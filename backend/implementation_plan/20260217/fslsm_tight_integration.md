# Backend: FSLSM Tight Integration into Learning Plan Generator

## Context

The current system uses FSLSM dimensions loosely — they are converted to text descriptions (`content_style`, `activity_type`) and passed to the LLM prompt. There is no structural enforcement: all learners get the same navigation model, quiz results are not evaluated for mastery, and session progression is unrestricted. This plan adds deterministic FSLSM-driven behavior to the learning path structure, mastery evaluation, and FSLSM-aware post-processing.

### FSLSM Guidelines to Implement

| Dimension | Pole | Guideline |
|-----------|------|-----------|
| Processing | Active (<=  -0.3) | Schedule frequent "Checkpoint Challenges" to break up long information blocks |
| Processing | Reflective (>= 0.3) | Build in "Thinking Time" buffers between sessions |
| Perception | Sensing (<= -0.3) | Follow sequence: Application -> Example -> Theory |
| Perception | Intuitive (>= 0.3) | Allow conceptual leaps, explore multiple theories simultaneously |
| Input | Visual (<= -0.3) | Ensure visual "Module Maps" are visible at every stage |
| Input | Verbal (>= 0.3) | Organize path around narrative or written discussions |
| Understanding | Sequential (<= -0.3) | Enforce "Mastery Lock": cannot proceed until mastered (quiz-evaluated) |
| Understanding | Global (>= 0.3) | Allow non-linear navigation between related modules |

---

## 1. Schema Changes

### 1A. Extend `SessionItem` with FSLSM-driven fields

**File:** `backend/modules/learning_plan_generator/schemas.py`

Add optional fields to `SessionItem` (all have defaults, backward compatible):

```python
from typing import Optional

class SessionItem(BaseModel):
    # ... existing fields ...

    # NEW: Mastery tracking
    mastery_score: Optional[float] = Field(None, ge=0, le=100, description="Quiz score %, None if not attempted")
    is_mastered: bool = Field(False, description="True if mastery_score >= mastery_threshold")
    mastery_threshold: float = Field(70.0, ge=0, le=100, description="Per-session threshold based on required proficiency")

    # NEW: FSLSM-driven structural fields
    has_checkpoint_challenges: bool = Field(False, description="Active learners: mid-session challenges")
    thinking_time_buffer_minutes: int = Field(0, ge=0, description="Reflective learners: buffer time")
    session_sequence_hint: Optional[str] = Field(None, description="'application-first' or 'theory-first'")
    navigation_mode: str = Field("linear", description="'linear' (sequential) or 'free' (global)")
```

### 1B. Add mastery configuration to `APP_CONFIG`

**File:** `backend/main.py`

Add to the `APP_CONFIG` dict:

```python
"mastery_threshold_default": 70,
"mastery_threshold_by_proficiency": {
    "beginner": 60,
    "intermediate": 70,
    "advanced": 80,
    "expert": 90,
},
"fslsm_activation_threshold": 0.3,
```

The per-session threshold is determined by the highest required proficiency level in that session's `desired_outcome_when_completed`. This makes mastery adaptive: beginner content needs 60% to pass, expert content needs 90%.

### 1C. Add `QuizResult` schema

**File:** `backend/modules/learning_plan_generator/schemas.py`

```python
class QuizResult(BaseModel):
    session_id: str
    total_questions: int = Field(..., ge=1)
    correct_answers: int = Field(..., ge=0)
    score_percentage: float = Field(..., ge=0, le=100)
```

---

## 2. Quiz Scoring and Mastery Evaluation

### 2A. New utility: `compute_quiz_score()`

**File (new):** `backend/utils/quiz_scorer.py`

Pure deterministic function (no LLM):

```python
def compute_quiz_score(quiz_data: dict, user_answers: dict) -> tuple[int, int, float]:
    """
    Score user answers against quiz data.
    Returns (correct_count, total_count, score_percentage).

    Scoring rules:
    - single_choice: exact match on correct_option index
    - multiple_choice: exact set match on correct_options indices
    - true_false: exact match on correct_answer boolean
    - short_answer: case-insensitive stripped match on expected_answer
    """
    total = 0
    correct = 0

    for q_type in ["single_choice_questions", "multiple_choice_questions",
                    "true_false_questions", "short_answer_questions"]:
        questions = quiz_data.get(q_type, [])
        answers = user_answers.get(q_type, [])
        for i, q in enumerate(questions):
            total += 1
            if i < len(answers) and answers[i] is not None:
                if q_type == "single_choice_questions":
                    if answers[i] == q["options"][q["correct_option"]]:
                        correct += 1
                elif q_type == "multiple_choice_questions":
                    correct_set = {q["options"][idx] for idx in q["correct_options"]}
                    if set(answers[i]) == correct_set:
                        correct += 1
                elif q_type == "true_false_questions":
                    expected = "True" if q["correct_answer"] else "False"
                    if str(answers[i]) == expected:
                        correct += 1
                elif q_type == "short_answer_questions":
                    if str(answers[i]).strip().lower() == q["expected_answer"].strip().lower():
                        correct += 1

    pct = (correct / total * 100) if total > 0 else 0.0
    return correct, total, pct


def get_mastery_threshold_for_session(session: dict, threshold_map: dict, default: float = 70.0) -> float:
    """
    Determine mastery threshold based on the highest proficiency level
    in the session's desired_outcome_when_completed.
    """
    proficiency_order = ["beginner", "intermediate", "advanced", "expert"]
    outcomes = session.get("desired_outcome_when_completed", [])
    if not outcomes:
        return default
    highest = max(
        (proficiency_order.index(o["level"]) for o in outcomes if o.get("level") in proficiency_order),
        default=0
    )
    level_name = proficiency_order[highest]
    return threshold_map.get(level_name, default)
```

### 2B. New endpoint: `POST /evaluate-mastery`

**File:** `backend/main.py` (endpoint) + `backend/api_schemas.py` (request schema)

Request schema:
```python
class MasteryEvaluationRequest(BaseModel):
    user_id: str
    goal_id: int
    session_index: int
    quiz_answers: dict  # {single_choice_questions: [...], multiple_choice_questions: [...], ...}
```

Endpoint logic:
1. Retrieve user state via `store.get_user_state(request.user_id)`
2. Get the goal and session from the learning path
3. Get cached quiz data from `document_caches[session_uid]["quizzes"]`
4. Score using `compute_quiz_score(quiz_data, request.quiz_answers)`
5. Determine per-session threshold using `get_mastery_threshold_for_session(session, APP_CONFIG["mastery_threshold_by_proficiency"])`
6. Set `is_mastered = score >= threshold`
7. Update `session["mastery_score"]` and `session["is_mastered"]` in user state
8. Persist via `store.put_user_state()`
9. Return `{score_percentage, is_mastered, threshold, correct_count, total_count, session_id}`

### 2C. New endpoint: `GET /session-mastery-status/{user_id}`

**File:** `backend/main.py`

Query param: `goal_id: int`

Returns list of mastery status objects for all sessions in the specified goal:
```json
[
  {
    "session_id": "Session 1",
    "is_mastered": true,
    "mastery_score": 85.0,
    "mastery_threshold": 70.0,
    "if_learned": true
  },
  ...
]
```

Used by frontend to determine navigation locks without needing the full user state.

---

## 3. FSLSM Post-Processing in Scheduler

### 3A. Deterministic post-processing function

**File:** `backend/modules/learning_plan_generator/agents/learning_path_scheduler.py`

New function `_apply_fslsm_overrides(learning_path: dict, learner_profile: dict) -> dict`:

```python
def _apply_fslsm_overrides(learning_path: dict, learner_profile: dict) -> dict:
    """
    Deterministic post-processing: enforce FSLSM structural rules
    regardless of what the LLM produced. Acts as safety net.
    """
    prefs = learner_profile if isinstance(learner_profile, dict) else {}
    dims = prefs.get("learning_preferences", {}).get("fslsm_dimensions", {})
    threshold = 0.3  # activation threshold

    # Import config for proficiency-based mastery thresholds
    # (passed in or imported from main)
    threshold_map = {"beginner": 60, "intermediate": 70, "advanced": 80, "expert": 90}

    for session in learning_path.get("learning_path", []):
        # Processing dimension
        proc = dims.get("fslsm_processing", 0)
        if proc <= -threshold:
            session["has_checkpoint_challenges"] = True
        elif proc >= threshold:
            session["thinking_time_buffer_minutes"] = max(session.get("thinking_time_buffer_minutes", 0), 10)

        # Perception dimension
        perc = dims.get("fslsm_perception", 0)
        if perc <= -threshold:
            session["session_sequence_hint"] = "application-first"
        elif perc >= threshold:
            session["session_sequence_hint"] = "theory-first"

        # Understanding dimension (CRITICAL: navigation mode)
        und = dims.get("fslsm_understanding", 0)
        if und >= threshold:
            session["navigation_mode"] = "free"
        else:
            session["navigation_mode"] = "linear"

        # Set per-session mastery threshold based on proficiency
        session["mastery_threshold"] = get_mastery_threshold_for_session(session, threshold_map)

    return learning_path
```

Call this in `schedule_session()`, `reflexion()`, and `reschedule()` after `LearningPath.model_validate()`:

```python
def schedule_session(self, input_dict: Dict[str, Any]) -> JSONDict:
    payload_dict = SessionSchedulePayload(**input_dict).model_dump()
    task_prompt = learning_path_scheduler_task_prompt_session
    raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
    validated_output = LearningPath.model_validate(raw_output)
    result = validated_output.model_dump()
    # NEW: apply FSLSM overrides deterministically
    learner_profile = input_dict.get("learner_profile", {})
    if isinstance(learner_profile, str):
        import json
        try:
            learner_profile = json.loads(learner_profile)
        except Exception:
            learner_profile = {}
    return _apply_fslsm_overrides(result, learner_profile)
```

Same pattern for `reflexion()` (needs profile from context) and `reschedule()` (has `learner_profile` in input).

### 3B. Prompt updates

**File:** `backend/modules/learning_plan_generator/prompts/learning_path_scheduling.py`

#### Update `learning_path_output_format` to include new fields:

```python
learning_path_output_format = """
{
    "learning_path": [
        {
            "id": "Session 1",
            "title": "Session Title",
            "abstract": "Brief overview of the session content (max 200 words)",
            "if_learned": false,
            "associated_skills": ["Skill 1", "Skill 2"],
            "desired_outcome_when_completed": [
                {"name": "Skill 1", "level": "intermediate"}
            ],
            "mastery_score": null,
            "is_mastered": false,
            "mastery_threshold": 70.0,
            "has_checkpoint_challenges": false,
            "thinking_time_buffer_minutes": 0,
            "session_sequence_hint": null,
            "navigation_mode": "linear"
        }
    ]
}
""".strip()
```

#### Add FSLSM rules section to `learning_path_scheduler_system_prompt`:

Insert after directive 2 ("Personalized"):

```
2b. **FSLSM-Driven Structure**: You MUST read `fslsm_dimensions` from the learner profile and apply these rules:
   - **Processing** (`fslsm_processing`):
     - If <= -0.3 (Active): Set `has_checkpoint_challenges: true`. Include "Checkpoint Challenge" activities in session abstracts to break up information blocks.
     - If >= 0.3 (Reflective): Set `thinking_time_buffer_minutes` to 10-15. Note "Reflection Period" in session abstracts. Avoid scheduling back-to-back high-intensity sessions.
   - **Perception** (`fslsm_perception`):
     - If <= -0.3 (Sensing): Set `session_sequence_hint: "application-first"`. Order content: Application -> Example -> Theory.
     - If >= 0.3 (Intuitive): Set `session_sequence_hint: "theory-first"`. Allow conceptual leaps across related theories.
   - **Input** (`fslsm_input`):
     - If <= -0.3 (Visual): Reference "Module Map" in session abstracts. Emphasize diagrams and visual overviews.
     - If >= 0.3 (Verbal): Frame sessions as narrative chapters with written discussions.
   - **Understanding** (`fslsm_understanding`):
     - If <= -0.3 (Sequential): Set `navigation_mode: "linear"` for ALL sessions. Each session builds strictly on the previous.
     - If >= 0.3 (Global): Set `navigation_mode: "free"` for ALL sessions. Sessions can be explored in any order.
     - Otherwise: default to `navigation_mode: "linear"`.
```

---

## 4. Backend Tests

### 4A. New: `backend/tests/test_quiz_scorer.py`

| Test | What it covers |
|------|----------------|
| `test_perfect_score` | All correct answers -> 100% |
| `test_zero_score` | All wrong answers -> 0% |
| `test_partial_score` | Mixed correct/wrong -> proportional score |
| `test_empty_answers` | No answers submitted -> 0% |
| `test_single_choice_scoring` | Correct option index matching |
| `test_multiple_choice_scoring` | Exact set match required |
| `test_true_false_scoring` | Boolean matching |
| `test_short_answer_case_insensitive` | Case and whitespace insensitive |

### 4B. New: `backend/tests/test_fslsm_overrides.py`

| Test | What it covers |
|------|----------------|
| `test_active_learner_gets_checkpoint_challenges` | processing=-0.7 -> has_checkpoint_challenges=True on all sessions |
| `test_reflective_learner_gets_thinking_time` | processing=0.7 -> thinking_time_buffer_minutes >= 10 |
| `test_sensing_gets_application_first` | perception=-0.5 -> session_sequence_hint="application-first" |
| `test_intuitive_gets_theory_first` | perception=0.5 -> session_sequence_hint="theory-first" |
| `test_sequential_gets_linear_nav` | understanding=-0.5 -> navigation_mode="linear" |
| `test_global_gets_free_nav` | understanding=0.5 -> navigation_mode="free" |
| `test_neutral_gets_defaults` | All dimensions at 0 -> linear, no challenges, no buffers |
| `test_overrides_apply_to_all_sessions` | All sessions in path are affected |
| `test_mastery_threshold_by_proficiency` | Beginner session -> 60%, expert session -> 90% |

### 4C. New: `backend/tests/test_mastery_evaluation.py`

| Test | What it covers |
|------|----------------|
| `test_mastery_pass` | Score >= threshold -> is_mastered=True |
| `test_mastery_fail` | Score < threshold -> is_mastered=False |
| `test_threshold_boundary` | Score exactly at threshold -> pass |
| `test_proficiency_based_threshold_beginner` | Beginner session uses 60% threshold |
| `test_proficiency_based_threshold_expert` | Expert session uses 90% threshold |
| `test_threshold_lookup_missing_level` | Unknown level falls back to default 70% |

### 4D. Update `docs/user_flows_test_plan.md`

Add two new flows:

**Flow 6 -- FSLSM-Driven Learning Path Adaptations**: Tests each dimension's structural effect on the learning path (checkpoint challenges, thinking time, sequence hints, navigation mode).

**Flow 7 -- Mastery Lock and Quiz-Based Mastery Evaluation**: Tests the Submit All quiz model, mastery scoring, per-session thresholds, sequential lock enforcement, and global free navigation.

---

## Implementation Order

| Step | What | Files | Dependencies |
|------|------|-------|-------------|
| 1 | Schema changes (1A, 1B, 1C) | `schemas.py`, `main.py` | None |
| 2 | Quiz scorer utility (2A) | `utils/quiz_scorer.py` (new) | None |
| 3 | Mastery endpoints (2B, 2C) | `main.py`, `api_schemas.py` | Steps 1, 2 |
| 4 | FSLSM post-processing (3A) | `learning_path_scheduler.py` | Step 1 |
| 5 | Prompt updates (3B) | `learning_path_scheduling.py` | Step 1 |
| 6 | Backend tests (4A, 4B, 4C) | `tests/` (new files) | Steps 2, 3, 4 |
| 7 | User flows doc (4D) | `docs/user_flows_test_plan.md` | All above |

---

## Verification

1. **Unit tests**: `python -m pytest backend/tests/test_quiz_scorer.py backend/tests/test_fslsm_overrides.py backend/tests/test_mastery_evaluation.py -v`
2. **Regression tests**: `python -m pytest backend/tests/ -v` (all existing tests must still pass)
3. **Schema backward compatibility**: Existing learning paths without new fields should still validate (all new fields have defaults)
