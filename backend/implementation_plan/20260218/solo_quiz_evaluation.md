# SOLO-Aligned Quiz Generation and LLM-Based Free-Text Evaluation — Backend

## Context

The current quiz system has three significant gaps:

1. **No SOLO-aware question types** — Every session generates the same question mix (3 single-choice in backend, 3+1+1+1 in frontend) regardless of the session's required proficiency level. A beginner session and an expert session get the same question types.

2. **No open-ended questions** — There is no question type that requires paragraph-length synthesis. The highest-order question is `short_answer`, which expects a brief factual answer (e.g., "Python").

3. **Brittle free-text evaluation** — `short_answer_questions` are scored via exact case-insensitive string match (`answer.strip().lower() == expected.strip().lower()`). A learner who writes a correct but differently-worded answer gets 0 credit. There is no semantic or SOLO-level evaluation.

This plan adds: (a) a graduated question-type mix driven by session proficiency, (b) a 5th `open_ended_questions` type for Relational/Extended Abstract levels, and (c) LLM-based evaluation of free-text responses against a SOLO rubric at quiz submission time.

---

## 1. Schema Changes

### 1A. New `OpenEndedQuestion` schema

**File:** `backend/modules/content_generator/schemas.py`

```python
class OpenEndedQuestion(BaseModel):
    question: str
    rubric: str  # SOLO-aligned rubric: what constitutes each SOLO level for this question
    example_answer: str  # Model answer at the Relational/Extended Abstract level
    explanation: str | None = None
```

### 1B. Extend `DocumentQuiz` with `open_ended_questions`

**File:** `backend/modules/content_generator/schemas.py`

```python
class DocumentQuiz(BaseModel):
    single_choice_questions: List[SingleChoiceQuestion] = Field(default_factory=list)
    multiple_choice_questions: List[MultipleChoiceQuestion] = Field(default_factory=list)
    true_false_questions: List[TrueFalseQuestion] = Field(default_factory=list)
    short_answer_questions: List[ShortAnswerQuestion] = Field(default_factory=list)
    open_ended_questions: List[OpenEndedQuestion] = Field(default_factory=list)  # NEW
```

### 1C. New `SOLOEvaluation` schema for LLM evaluation results

**File (new):** `backend/utils/solo_evaluator.py` (schema defined here alongside the evaluator)

```python
class SOLOEvaluation(BaseModel):
    solo_level: str  # "prestructural" | "unistructural" | "multistructural" | "relational" | "extended_abstract"
    score: float  # 0.0–1.0 normalized score
    feedback: str  # Qualitative feedback for the learner
```

---

## 2. Graduated Question Mix

### 2A. Question mix configuration

**File:** `backend/main.py` — Add to `APP_CONFIG`:

```python
"quiz_mix_by_proficiency": {
    "beginner": {
        "single_choice_count": 4,
        "multiple_choice_count": 0,
        "true_false_count": 1,
        "short_answer_count": 0,
        "open_ended_count": 0,
    },
    "intermediate": {
        "single_choice_count": 2,
        "multiple_choice_count": 2,
        "true_false_count": 1,
        "short_answer_count": 0,
        "open_ended_count": 0,
    },
    "advanced": {
        "single_choice_count": 1,
        "multiple_choice_count": 1,
        "true_false_count": 0,
        "short_answer_count": 2,
        "open_ended_count": 1,
    },
    "expert": {
        "single_choice_count": 0,
        "multiple_choice_count": 1,
        "true_false_count": 0,
        "short_answer_count": 1,
        "open_ended_count": 3,
    },
},
```

### 2B. New utility: `get_quiz_mix_for_session()`

**File:** `backend/utils/quiz_scorer.py`

```python
def get_quiz_mix_for_session(session, quiz_mix_config):
    """Determine question type counts from the session's highest proficiency level."""
    # Reuse same logic as get_mastery_threshold_for_session to find highest proficiency
    # Return the corresponding mix dict from quiz_mix_config
```

### 2C. Update `create_learning_content_with_llm()` to use graduated mix

**File:** `backend/modules/content_generator/agents/learning_content_creator.py`

Replace the hardcoded counts (lines 115-122) with a call to `get_quiz_mix_for_session()`, passing the `learning_session` dict. This requires the session's `desired_outcome_when_completed` to be available.

### 2D. New endpoint: `GET /quiz-mix/{user_id}`

**File:** `backend/main.py`

Query params: `goal_id`, `session_index`. Returns the question counts dict for that session based on its proficiency level. This keeps the proficiency-to-mix logic on the backend.

---

## 3. Quiz Generation Prompt Updates

### 3A. Update output format to include `open_ended_questions`

**File:** `backend/modules/content_generator/prompts/document_quiz_generator.py`

Add to `document_quiz_output_format`:
```json
"open_ended_questions": [
    {
        "question": "Explain how X relates to Y and predict what would happen if Z.",
        "rubric": "Prestructural: irrelevant/no answer. Unistructural: mentions one concept. Multistructural: lists multiple concepts without connecting them. Relational: integrates concepts and explains relationships. Extended Abstract: generalizes to new contexts or predicts outcomes.",
        "example_answer": "A model answer demonstrating Relational or Extended Abstract thinking...",
        "explanation": "Key points that should be addressed..."
    }
]
```

### 3B. Update system prompt with SOLO-aligned directives

**File:** `backend/modules/content_generator/prompts/document_quiz_generator.py`

Add a new directive (between existing directives 3 and 4):

```
3b. **SOLO-Aligned Question Design**:
    - Single choice / True-False: Test recall and recognition (Unistructural level).
    - Multiple choice: Test identification of multiple relevant aspects (Multistructural level).
    - Short answer: Test ability to explain relationships briefly (Relational level).
    - Open-ended: Require synthesis, integration, or generalization (Relational / Extended Abstract level).
      Each open-ended question MUST include a `rubric` field that describes what a response at each SOLO level looks like for that specific question. Also include an `example_answer` showing a Relational or Extended Abstract response.
```

### 3C. Add `open_ended_count` to task prompt and `DocumentQuizPayload`

**File:** `backend/modules/content_generator/prompts/document_quiz_generator.py`
**File:** `backend/modules/content_generator/agents/document_quiz_generator.py`

Add `open_ended_count` parameter to the payload and task prompt template.

---

## 4. SOLO Evaluator (LLM-Based Free-Text Evaluation)

### 4A. New module: `backend/utils/solo_evaluator.py`

This is the core new component. Contains:

```python
SOLO_EVALUATION_PROMPT = """
You are a pedagogical assessment agent using the SOLO Taxonomy to evaluate student responses.

## SOLO Taxonomy Rubric

Given the question, the rubric, and the student's response, classify the response into one of five SOLO levels:

1. **Prestructural** (score: 0.0): The student misses the point entirely or provides irrelevant information.
2. **Unistructural** (score: 0.25): The response focuses on one relevant aspect but lacks depth or detail.
3. **Multistructural** (score: 0.5): The response identifies several relevant aspects but treats them as independent facts without integration.
4. **Relational** (score: 0.75): The response integrates separate parts into a coherent whole, showing how they relate to one another.
5. **Extended Abstract** (score: 1.0): The response generalizes the integrated whole to new, untaught contexts or makes predictions.

## Input

**Question:** {question}

**Question-Specific Rubric:** {rubric}

**Example Answer (Relational/Extended Abstract):** {example_answer}

**Student Response:** {student_response}

## Output

Return a JSON object:
{
    "solo_level": "one of: prestructural, unistructural, multistructural, relational, extended_abstract",
    "score": <float 0.0 to 1.0>,
    "feedback": "Brief qualitative feedback explaining the classification and how the student could improve."
}
"""


def evaluate_free_text_response(llm, question, rubric, example_answer, student_response) -> SOLOEvaluation:
    """Evaluate a single free-text response using SOLO taxonomy via LLM."""
    # Format prompt, call LLM, parse JSON response, return SOLOEvaluation


def evaluate_short_answer_response(llm, question, expected_answer, student_response) -> tuple[bool, str]:
    """Evaluate a short answer using LLM semantic matching (not exact string match).

    Returns (is_correct: bool, feedback: str).
    Uses a simpler prompt: 'Does the student response convey the same meaning as the expected answer?'
    """
```

### 4B. Short answer semantic evaluation prompt

For short answers, replace the brittle exact-match with a lightweight LLM call:

```
Given the question and expected answer, determine if the student's response is correct.
The response does not need to match word-for-word — accept any answer that conveys the same meaning.

Question: {question}
Expected Answer: {expected_answer}
Student Response: {student_response}

Return JSON: {"is_correct": true/false, "feedback": "brief explanation"}
```

---

## 5. Quiz Scorer Updates

### 5A. Update `compute_quiz_score()` for hybrid scoring

**File:** `backend/utils/quiz_scorer.py`

The function currently handles 4 deterministic question types. It needs to:
- Continue scoring single_choice, multiple_choice, true_false deterministically (no change)
- Accept pre-evaluated results for short_answer and open_ended (evaluated by LLM before scoring)

New signature:
```python
def compute_quiz_score(
    quiz_data: Dict[str, Any],
    user_answers: Dict[str, Any],
    llm_evaluations: Dict[str, Any] | None = None,  # NEW: pre-computed LLM results
) -> Tuple[int, int, float]:
```

The `llm_evaluations` dict contains:
```python
{
    "short_answer_evaluations": [{"is_correct": True, "feedback": "..."}, ...],
    "open_ended_evaluations": [{"solo_level": "relational", "score": 0.75, "feedback": "..."}, ...],
}
```

Scoring logic:
- **Short answer**: Use `llm_evaluations["short_answer_evaluations"][i]["is_correct"]` instead of exact string match
- **Open-ended**: Use `llm_evaluations["open_ended_evaluations"][i]["score"]` as a fractional score (0.0–1.0 contributing proportionally to the total)

### 5B. Backward compatibility

If `llm_evaluations` is `None`, fall back to the current behavior (exact string match for short answers, skip open_ended). This ensures existing cached quizzes without open_ended questions still work.

---

## 6. Endpoint Changes

### 6A. Update `POST /evaluate-mastery`

**File:** `backend/main.py`

Updated flow:
1. Retrieve quiz data from document cache (unchanged)
2. Score deterministic types (single_choice, multiple_choice, true_false) — unchanged
3. **NEW:** If quiz has `short_answer_questions` with user answers, call `evaluate_short_answer_response()` for each via LLM
4. **NEW:** If quiz has `open_ended_questions` with user answers, call `evaluate_free_text_response()` for each via LLM
5. Pass LLM evaluation results to `compute_quiz_score()`
6. Determine threshold and mastery (unchanged)
7. **NEW:** Include `solo_evaluations` in the response for frontend to display

Updated response:
```python
{
    "score_percentage": 85.0,
    "is_mastered": True,
    "threshold": 70,
    "correct_count": 4,
    "total_count": 5,
    "session_id": "Session 1",
    # NEW fields:
    "short_answer_feedback": [{"is_correct": True, "feedback": "..."}, ...],
    "open_ended_feedback": [
        {"solo_level": "relational", "score": 0.75, "feedback": "Good integration of concepts..."},
        ...
    ],
}
```

### 6B. New endpoint: `GET /quiz-mix/{user_id}`

**File:** `backend/main.py`

```python
@app.get("/quiz-mix/{user_id}")
async def get_quiz_mix(user_id: str, goal_id: int, session_index: int):
    # Get session from user state
    # Call get_quiz_mix_for_session(session, APP_CONFIG["quiz_mix_by_proficiency"])
    # Return the question counts dict
```

---

## 7. Backend Tests

### 7A. New: `backend/tests/test_solo_evaluator.py`

| Test | Coverage |
|------|----------|
| `test_prestructural_response` | Irrelevant response → score 0.0 |
| `test_unistructural_response` | Single-aspect response → score 0.25 |
| `test_relational_response` | Integrated response → score 0.75 |
| `test_extended_abstract_response` | Generalizing response → score 1.0 |
| `test_short_answer_semantic_correct` | Semantically equivalent → is_correct=True |
| `test_short_answer_semantic_wrong` | Wrong meaning → is_correct=False |

Note: These tests require LLM mocking. Use the same mock patterns as `test_onboarding_api.py`.

### 7B. Update: `backend/tests/test_quiz_scorer.py`

| Test | Coverage |
|------|----------|
| `test_open_ended_scoring_with_evaluations` | Open-ended fractional scores contribute to total |
| `test_short_answer_with_llm_evaluation` | LLM-evaluated short answer overrides exact match |
| `test_backward_compat_no_llm_evaluations` | None evaluations falls back to exact match |
| `test_mixed_types_with_open_ended` | All 5 types scored together |

### 7C. New: `backend/tests/test_quiz_mix.py`

| Test | Coverage |
|------|----------|
| `test_beginner_mix` | beginner → 4 SC, 0 MC, 1 TF, 0 SA, 0 OE |
| `test_intermediate_mix` | intermediate → 2 SC, 2 MC, 1 TF, 0 SA, 0 OE |
| `test_advanced_mix` | advanced → 1 SC, 1 MC, 0 TF, 2 SA, 1 OE |
| `test_expert_mix` | expert → 0 SC, 1 MC, 0 TF, 1 SA, 3 OE |
| `test_mixed_proficiency_uses_highest` | Session with beginner+expert outcomes → expert mix |
| `test_empty_outcomes_uses_beginner` | No outcomes → beginner mix (default) |

---

## Implementation Order

| Step | What | Files | Dependencies |
|------|------|-------|-------------|
| 1 | Schema: OpenEndedQuestion + update DocumentQuiz | `content_generator/schemas.py` | None |
| 2 | Quiz mix config + utility | `main.py`, `utils/quiz_scorer.py` | None |
| 3 | Quiz mix endpoint | `main.py` | 2 |
| 4 | Quiz generation prompt updates | `prompts/document_quiz_generator.py`, `agents/document_quiz_generator.py` | 1 |
| 5 | SOLO evaluator (new module) | `utils/solo_evaluator.py` (new) | None |
| 6 | Update quiz scorer for hybrid scoring | `utils/quiz_scorer.py` | 5 |
| 7 | Update /evaluate-mastery endpoint | `main.py` | 5, 6 |
| 8 | Backend tests | `tests/test_solo_evaluator.py`, `tests/test_quiz_mix.py`, update `tests/test_quiz_scorer.py` | 2, 5, 6 |

---

## Verification

1. **Unit tests**: `python -m pytest backend/tests/test_quiz_mix.py backend/tests/test_quiz_scorer.py -v`
2. **SOLO evaluator tests** (requires LLM mock): `python -m pytest backend/tests/test_solo_evaluator.py -v`
3. **All backend tests** (regression): `python -m pytest backend/tests/ -v`
4. **Manual test — Beginner session**: Select beginner-level goal, generate content, verify quiz has 4 single-choice + 1 true/false, no open-ended
5. **Manual test — Expert session**: Select expert-level goal, verify quiz has mostly open-ended questions
6. **Manual test — Open-ended evaluation**: Submit an open-ended response, verify SOLO-level feedback is returned with score and qualitative feedback
7. **Manual test — Short answer semantic**: Submit a semantically correct but differently-worded short answer, verify it is accepted
8. **Manual test — Backward compatibility**: Load a session with old cached quiz data (no open_ended), verify it still works
