# SOLO-Aligned Quiz Generation and LLM-Based Free-Text Evaluation — Frontend

## Context

The current quiz system has three significant gaps:

1. **No SOLO-aware question types** — Every session generates the same question mix (3+1+1+1) regardless of the session's required proficiency level.

2. **No open-ended questions** — There is no question type that requires paragraph-length synthesis.

3. **No SOLO-level feedback** — After quiz submission, the learner only sees a percentage score. There is no qualitative feedback about the depth of understanding demonstrated.

This plan adds: (a) frontend calls to get the graduated question mix from the backend, (b) rendering for the new `open_ended_questions` type, and (c) SOLO-level feedback display after quiz submission.

**Depends on:** Backend implementation plan `backend/implementation_plan/20260217/solo_quiz_evaluation.md`

---

## 1. Frontend API Changes

### 1A. New API call: `get_quiz_mix()`

**File:** `frontend/utils/request_api.py`

```python
def get_quiz_mix(user_id, goal_id, session_index):
    """Get the SOLO-aligned question mix for a session."""
    url = f"{backend_endpoint}quiz-mix/{user_id}?goal_id={goal_id}&session_index={session_index}"
    # GET request, return dict of counts
```

### 1B. Update `generate_document_quizzes()` call

**File:** `frontend/utils/request_api.py`

Add `open_ended_count` parameter to the existing `generate_document_quizzes()` function.

### 1C. Update `evaluate_mastery()` response handling

The response now includes `short_answer_feedback` and `open_ended_feedback`. Store these in `mastery_status` for display.

---

## 2. Knowledge Document Page Updates

### 2A. Use graduated quiz mix when generating quizzes

**File:** `frontend/pages/knowledge_document.py`

Replace the hardcoded counts (lines 266-274):
```python
# Before:
quizzes = generate_document_quizzes(..., single_choice_count=3, multiple_choice_count=1, ...)

# After:
quiz_mix = get_quiz_mix(user_id, goal_id, session_index)
quizzes = generate_document_quizzes(
    ...,
    single_choice_count=quiz_mix["single_choice_count"],
    multiple_choice_count=quiz_mix["multiple_choice_count"],
    true_false_count=quiz_mix["true_false_count"],
    short_answer_count=quiz_mix["short_answer_count"],
    open_ended_count=quiz_mix["open_ended_count"],
)
```

### 2B. Render open-ended questions

**File:** `frontend/pages/knowledge_document.py`

In `render_questions()`, add a new section after short answer rendering:

```python
# Open-ended questions
for i, q in enumerate(quiz_data.get("open_ended_questions", [])):
    q_num += 1
    st.write(f"**{q_num}. {q['question']}**")
    st.caption("Write a detailed response demonstrating your understanding.")
    user_answer = st.text_area(
        "Your Response", key=f"oe_{session_uid}_{i}",
        height=150, label_visibility="hidden", disabled=quiz_submitted,
    )
    answers["open_ended_questions"][i] = user_answer if user_answer else None
```

### 2C. Update answer storage initialization

**File:** `frontend/pages/knowledge_document.py`

Add `open_ended_questions` to the answer initialization dict in `render_questions()`:
```python
st.session_state.setdefault("quiz_answers", {})[session_uid] = {
    "single_choice_questions": [...],
    "multiple_choice_questions": [...],
    "true_false_questions": [...],
    "short_answer_questions": [...],
    "open_ended_questions": [None] * len(quiz_data.get("open_ended_questions", [])),  # NEW
}
```

### 2D. Display SOLO feedback after submission

**File:** `frontend/pages/knowledge_document.py`

In `_render_quiz_explanations()`, add SOLO-level feedback for open-ended and short-answer questions:

**Short answer feedback:**
- Show "Correct" or "Incorrect" based on LLM semantic evaluation
- Show the LLM's feedback explanation

**Open-ended SOLO feedback:**
- Show SOLO level with color-coded badge:
  - Extended Abstract: green badge
  - Relational: blue badge
  - Multistructural: yellow badge
  - Unistructural: orange badge
  - Prestructural: red badge
- Show the score (0.0–1.0)
- Show qualitative feedback explaining the classification and how to improve

### 2E. Store SOLO feedback in mastery_status

When the `evaluate_mastery` response comes back with `open_ended_feedback` and `short_answer_feedback`, store them in `mastery_status[session_uid]` so they persist across Streamlit reruns:

```python
st.session_state["mastery_status"][session_uid] = {
    "score": result["score_percentage"],
    "is_mastered": result["is_mastered"],
    "threshold": result["threshold"],
    "short_answer_feedback": result.get("short_answer_feedback", []),      # NEW
    "open_ended_feedback": result.get("open_ended_feedback", []),          # NEW
}
```

### 2F. Add spinner/loading state for LLM evaluation

Since open-ended evaluation requires LLM calls (adds ~3-5s latency), wrap the submission in a spinner:

```python
with st.spinner("Evaluating your responses..."):
    result = evaluate_mastery(...)
```

---

## Implementation Order

| Step | What | Files | Dependencies |
|------|------|-------|-------------|
| 1 | Frontend API: get_quiz_mix, update generate_document_quizzes | `frontend/utils/request_api.py` | Backend endpoints ready |
| 2 | Frontend: graduated mix + open-ended rendering + SOLO feedback | `frontend/pages/knowledge_document.py` | Step 1 |
| 3 | Update user flows test plan | `docs/user_flows_test_plan.md` | All |

---

## Verification

1. **Manual test — Beginner session**: Select beginner-level goal, generate content, verify quiz has 4 single-choice + 1 true/false, no open-ended
2. **Manual test — Expert session**: Select expert-level goal, verify quiz has mostly open-ended questions with text area inputs
3. **Manual test — Open-ended evaluation**: Submit an open-ended response, verify SOLO-level feedback is displayed with color-coded badge, score, and qualitative feedback
4. **Manual test — Short answer semantic**: Submit a semantically correct but differently-worded short answer, verify it is accepted (green) with feedback
5. **Manual test — Backward compatibility**: Load a session with old cached quiz data (no open_ended), verify it still works
6. **Manual test — Loading state**: Submit quiz with open-ended questions, verify spinner shows during LLM evaluation
