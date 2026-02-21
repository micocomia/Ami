# SOLO-Aligned Quiz Generation and LLM-Based Free-Text Evaluation — Frontend

**Date**: 2026-02-18
**Sprint**: 3 — Agentic Content Generator
**Branch**: `sprint-3-agentic-content-generator`

> **Note:** A draft of this plan was written in `frontend/implementation_plan/20260217/solo_quiz_evaluation.md`.
> This file documents the final implemented version, including changes to design decisions made during implementation.

---

## Context

Three gaps in the quiz system are addressed by this sprint:

1. **Hardcoded question mix** — Every session generated the same counts (3 single-choice + 1 multiple-choice + 1 true/false + 1 short-answer) regardless of the session's required proficiency level. Beginner and expert sessions were treated identically.

2. **No open-ended question type** — The highest-order question was `short_answer`, which accepts a single-line factual answer. No question type required paragraph-length synthesis or integration of concepts.

3. **No SOLO-level feedback** — After submission learners only saw a percentage score. There was no qualitative feedback about the depth of understanding demonstrated, nor any indication of how to improve.

This plan adds: (a) a `get_quiz_mix()` API call to retrieve the proficiency-matched question counts from the backend, (b) an `open_ended_count` parameter on `generate_document_quizzes()`, (c) rendering for the new `open_ended_questions` type with `st.text_area`, (d) a loading spinner on quiz submission, (e) storage of `short_answer_feedback` and `open_ended_feedback` from the evaluation response, and (f) colour-coded SOLO-level feedback display in the explanations panel.

**Depends on:** `backend/implementation_plan/20260218/solo_quiz_evaluation.md`

---

## 1. Frontend API Changes

**File:** `frontend/utils/request_api.py`

### 1A. New function: `get_quiz_mix()`

```python
def get_quiz_mix(user_id, goal_id, session_index):
    """Get SOLO-aligned question type counts for a session from the backend.

    Returns a dict with keys: single_choice_count, multiple_choice_count,
    true_false_count, short_answer_count, open_ended_count.
    Falls back to a standard beginner mix if the endpoint is unavailable.
    """
    url = f"{backend_endpoint}quiz-mix/{user_id}?goal_id={goal_id}&session_index={session_index}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    # Fallback: standard mix (same as previous hardcoded behaviour)
    return {
        "single_choice_count": 3,
        "multiple_choice_count": 1,
        "true_false_count": 1,
        "short_answer_count": 1,
        "open_ended_count": 0,
    }
```

The fallback values match the pre-Sprint-3 hardcoded counts, so cached sessions generated before this sprint continue to work identically if the backend endpoint is unreachable.

### 1B. Update `generate_document_quizzes()` — add `open_ended_count`

```python
# Before:
def generate_document_quizzes(
    learner_profile, learning_document,
    single_choice_count, multiple_choice_count, true_false_count, short_answer_count,
    llm_type=None, method_name=None,
):

# After:
def generate_document_quizzes(
    learner_profile, learning_document,
    single_choice_count, multiple_choice_count, true_false_count, short_answer_count,
    open_ended_count=0,          # NEW — defaults to 0 for backward compatibility
    llm_type=None, method_name=None,
):
    data = {
        ...
        "open_ended_count": open_ended_count,   # NEW
    }
```

The default `open_ended_count=0` means any existing call sites that do not pass this argument are unaffected.

### 1C. `evaluate_mastery()` — no signature change

The `/evaluate-mastery` endpoint now returns two additional fields in its response body:
- `short_answer_feedback`: list of `{"is_correct": bool, "feedback": str}` dicts
- `open_ended_feedback`: list of `{"solo_level": str, "score": float, "feedback": str}` dicts

The existing `evaluate_mastery()` wrapper already returns the full response dict (`return response if response else None`), so no changes to `request_api.py` are needed for these fields. They are read in `knowledge_document.py` when storing the mastery result.

---

## 2. Knowledge Document Page Updates

**File:** `frontend/pages/knowledge_document.py`

### 2A. Import

```python
from utils.request_api import (
    ..., evaluate_mastery,
    get_quiz_mix,   # NEW
)
```

### 2B. `render_content_preparation()` — dynamic quiz mix

Replace the hardcoded counts in Stage 4:

```python
# Before:
quizzes = generate_document_quizzes(
    goal["learner_profile"],
    learning_document,
    single_choice_count=3,
    multiple_choice_count=1,
    true_false_count=1,
    short_answer_count=1,
    llm_type="gpt4o"
)

# After:
quiz_mix = get_quiz_mix(
    user_id=st.session_state.get("userId", ""),
    goal_id=st.session_state["selected_goal_id"],
    session_index=selected_sid,
)
quizzes = generate_document_quizzes(
    goal["learner_profile"],
    learning_document,
    single_choice_count=quiz_mix["single_choice_count"],
    multiple_choice_count=quiz_mix["multiple_choice_count"],
    true_false_count=quiz_mix["true_false_count"],
    short_answer_count=quiz_mix["short_answer_count"],
    open_ended_count=quiz_mix.get("open_ended_count", 0),
    llm_type="gpt4o"
)
```

`get_quiz_mix()` is called within the Stage 4 spinner, so any network latency is hidden inside the existing loading state.

### 2C. `render_questions()` — answer storage initialisation

Add `open_ended_questions` to the session answer dict:

```python
st.session_state.setdefault("quiz_answers", {})[session_uid] = {
    "single_choice_questions":  [None] * len(quiz_data.get("single_choice_questions", [])),
    "multiple_choice_questions": [[] for _ in quiz_data.get("multiple_choice_questions", [])],
    "true_false_questions":     [None] * len(quiz_data.get("true_false_questions", [])),
    "short_answer_questions":   [None] * len(quiz_data.get("short_answer_questions", [])),
    "open_ended_questions":     [None] * len(quiz_data.get("open_ended_questions", [])),   # NEW
}
```

The `dict.get(..., [])` pattern means that when a cached quiz has no `open_ended_questions` key (pre-Sprint-3 cache), the list initialises to `[]` and nothing breaks.

### 2D. `render_questions()` — render open-ended questions

After the short-answer section, add:

```python
# Open-ended questions (Sprint 3: SOLO taxonomy — Relational / Extended Abstract)
if quiz_data.get("open_ended_questions"):
    st.divider()
    st.caption(
        "The following questions require a detailed written response "
        "and will be evaluated using the SOLO Taxonomy."
    )
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

`disabled=quiz_submitted` mirrors the behaviour of all other question types — inputs lock after the quiz is submitted.

### 2E. `render_questions()` — spinner on submit

LLM evaluation of short-answer and open-ended responses adds ~3–8 s of latency. Wrap the `evaluate_mastery` call in a spinner:

```python
# Before:
if st.button("Submit Quiz", ...):
    result = evaluate_mastery(...)

# After:
if st.button("Submit Quiz", ...):
    with st.spinner("Evaluating your responses..."):
        result = evaluate_mastery(...)
```

### 2F. `render_questions()` — store SOLO feedback in mastery_status

When storing the evaluation result, include the two new feedback fields:

```python
st.session_state.setdefault("mastery_status", {})[session_uid] = {
    "score":                result["score_percentage"],
    "is_mastered":          result["is_mastered"],
    "threshold":            result["threshold"],
    "short_answer_feedback": result.get("short_answer_feedback", []),   # NEW
    "open_ended_feedback":   result.get("open_ended_feedback", []),     # NEW
}
```

Using `.get(..., [])` ensures backward compatibility: if the backend returns neither field (e.g., when there are no free-text questions), the stored dicts simply have empty lists.

### 2G. `_render_quiz_explanations()` — accept mastery_info and display SOLO feedback

**Signature change:**

```python
# Before:
def _render_quiz_explanations(quiz_data):

# After:
def _render_quiz_explanations(quiz_data, mastery_info=None):
```

`mastery_info=None` as the default means any existing call site that omits the argument continues to work.

**Short answer — semantic evaluation feedback:**

After the expected-answer line, display the LLM's semantic evaluation result:

```python
sa_feedback = (mastery_info or {}).get("short_answer_feedback", [])
for i, q in enumerate(quiz_data.get("short_answer_questions", [])):
    q_num += 1
    st.write(f"**Q{q_num}.** Expected: {q['expected_answer']}")
    st.write(f"  {q['explanation']}")
    if i < len(sa_feedback):
        fb = sa_feedback[i]
        icon  = "✓" if fb.get("is_correct") else "✗"
        color = "#22CC66" if fb.get("is_correct") else "#FF4444"
        st.markdown(
            f"<span style='color:{color}'>{icon} {fb.get('feedback', '')}</span>",
            unsafe_allow_html=True,
        )
```

**Open-ended — SOLO-level feedback:**

```python
_SOLO_LEVEL_COLORS = {
    "prestructural":    "#FF4444",
    "unistructural":    "#FF8800",
    "multistructural":  "#DDAA00",
    "relational":       "#2288FF",
    "extended_abstract":"#22CC66",
}

_SOLO_LEVEL_LABELS = {
    "prestructural":    "Prestructural",
    "unistructural":    "Unistructural",
    "multistructural":  "Multistructural",
    "relational":       "Relational",
    "extended_abstract":"Extended Abstract",
}

oe_feedback = (mastery_info or {}).get("open_ended_feedback", [])
for i, q in enumerate(quiz_data.get("open_ended_questions", [])):
    q_num += 1
    st.write(f"**Q{q_num}.** (Open-ended)")
    with st.container(border=True):
        st.caption("Rubric")
        st.write(q.get("rubric", ""))
        if q.get("example_answer"):
            st.caption("Example answer")
            st.write(q["example_answer"])
    if i < len(oe_feedback):
        fb     = oe_feedback[i]
        solo   = fb.get("solo_level", "")
        score  = fb.get("score", 0.0)
        label  = _SOLO_LEVEL_LABELS.get(solo, solo.title())
        color  = _SOLO_LEVEL_COLORS.get(solo, "#999999")
        st.markdown(
            f"**SOLO Level:** <span style='color:{color};font-weight:bold'>{label}</span>"
            f" — Score: {score:.0%}",
            unsafe_allow_html=True,
        )
        st.write(f"Feedback: {fb.get('feedback', '')}")
```

**Call-site updates** — both call sites in `render_questions()` are updated to pass `mastery_info`:

```python
# Was:
_render_quiz_explanations(quiz_data)

# Now:
_render_quiz_explanations(quiz_data, mastery_info)
```

---

## 3. SOLO Level Colour Scheme

| SOLO Level | Colour | Rationale |
|---|---|---|
| Prestructural | Red `#FF4444` | Danger — response missed the point entirely |
| Unistructural | Orange `#FF8800` | Warning — only one aspect addressed |
| Multistructural | Amber `#DDAA00` | Caution — multiple facts but not integrated |
| Relational | Blue `#2288FF` | Good — concepts integrated into a coherent whole |
| Extended Abstract | Green `#22CC66` | Excellent — generalised to new contexts |

Colours use hex values rather than Streamlit theme variables to guarantee consistency regardless of light/dark mode.

---

## Implementation Order

| Step | What | File | Notes |
|------|------|------|-------|
| 1 | Add `get_quiz_mix()` | `utils/request_api.py` | New GET endpoint wrapper |
| 2 | Add `open_ended_count` to `generate_document_quizzes()` | `utils/request_api.py` | Default 0 — backward compatible |
| 3 | Dynamic quiz mix in `render_content_preparation()` | `pages/knowledge_document.py` | Depends on Steps 1–2 |
| 4 | `open_ended_questions` in answer storage | `pages/knowledge_document.py` | Depends on Step 3 |
| 5 | Open-ended question rendering | `pages/knowledge_document.py` | Depends on Step 4 |
| 6 | Spinner on submit + SOLO feedback storage | `pages/knowledge_document.py` | Depends on Step 5 |
| 7 | SOLO feedback display in `_render_quiz_explanations()` | `pages/knowledge_document.py` | Depends on Step 6 |
| 8 | Update user flows test plan | `docs/user_flows_test_plan.md` | Flows 11, 12 added; Flows 6, 7 updated |

---

## Verification

1. **Beginner session quiz mix**: Select beginner-level goal, generate content, reach the quiz. Verify 4 single-choice + 1 true/false. No open-ended text areas visible.
2. **Expert session quiz mix**: Select expert-level goal, generate content. Verify 1 multiple-choice + 1 short-answer + 3 open-ended text areas (height ≈ 150 px each). Caption "Write a detailed response…" above each.
3. **Open-ended input locking**: Submit quiz. Verify all `st.text_area` inputs become disabled after submission.
4. **Spinner**: Submit quiz containing open-ended questions. Verify "Evaluating your responses…" spinner appears for the duration of the LLM evaluation (~3–8 s).
5. **SOLO feedback — Extended Abstract**: Submit a high-quality response demonstrating generalisation. View explanations → green "Extended Abstract" label, score 100%, qualitative feedback.
6. **SOLO feedback — Prestructural**: Submit an irrelevant or blank response. View explanations → red "Prestructural" label, score 0%.
7. **Short-answer semantic**: Submit "A high-level programming language" for a question expecting "Python". Verify green ✓ with feedback accepting the answer.
8. **Short-answer wrong meaning**: Submit "A reptile" to the same question. Verify red ✗ with feedback.
9. **Backward compatibility — no open_ended key**: Load a session cached before Sprint 3. Verify quiz renders with 4 existing question types, no open-ended section, no UI errors.
10. **Backward compatibility — no open_ended_feedback**: Submit a legacy quiz. Verify `open_ended_feedback` defaults to `[]` in `mastery_status`. No `KeyError` or crash in `_render_quiz_explanations()`.
