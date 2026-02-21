# Frontend: FSLSM Tight Integration into Learning Plan Generator

## Context

The current frontend treats all learners identically: all sessions are navigable, quizzes show per-question feedback but scores are not tracked, and session completion is a simple toggle. This plan adds FSLSM-driven UI adaptations including mastery lock navigation, a Submit All quiz model with mastery evaluation, visual module maps, narrative overviews, and checkpoint/buffer indicators.

### FSLSM Guidelines to Implement

| Dimension | Pole | Frontend Behavior |
|-----------|------|-------------------|
| Processing | Active (<= -0.3) | Show "Checkpoint Challenges" indicators on session cards |
| Processing | Reflective (>= 0.3) | Show "Thinking Time" buffer recommendations between sessions |
| Perception | Sensing (<= -0.3) | Sessions labeled "Application -> Example -> Theory" |
| Perception | Intuitive (>= 0.3) | Sessions labeled "Theory-first / Conceptual exploration" |
| Input | Visual (<= -0.3) | Display visual "Module Map" at every stage |
| Input | Verbal (>= 0.3) | Display narrative/chapter-style learning journey |
| Understanding | Sequential (<= -0.3) | **Mastery Lock**: sessions locked until previous is mastered |
| Understanding | Global (>= 0.3) | **Free navigation**: all sessions accessible in any order |

---

## 5. State Management Updates

### 5A. New state keys

**File:** `frontend/utils/state.py`

Add to `PERSIST_KEYS` and `initialize_session_state()`:

```python
# In PERSIST_KEYS list:
"quiz_answers",      # {session_uid: {single_choice_questions: [...], ...}}
"mastery_status",    # {session_uid: {score: float, is_mastered: bool, threshold: float}}

# In initialize_session_state():
if "quiz_answers" not in st.session_state:
    st.session_state["quiz_answers"] = {}
if "mastery_status" not in st.session_state:
    st.session_state["mastery_status"] = {}
```

### 5B. New API calls

**File:** `frontend/utils/request_api.py`

```python
def evaluate_mastery(user_id: str, goal_id: int, session_index: int, quiz_answers: dict):
    """Submit quiz answers for mastery evaluation."""
    data = {
        "user_id": user_id,
        "goal_id": goal_id,
        "session_index": session_index,
        "quiz_answers": quiz_answers,
    }
    response = make_post_request("evaluate-mastery", data)
    return response if response else None


def get_session_mastery_status(user_id: str, goal_id: int):
    """Get mastery status for all sessions in a goal."""
    url = f"{backend_endpoint}session-mastery-status/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None
```

---

## 6. Knowledge Document Page -- Submit All Quiz Model

**File:** `frontend/pages/knowledge_document.py`

### 6A. Replace per-question feedback with Submit All

**Current behavior:** Each question shows correct/incorrect immediately after answering.

**New behavior:**
1. Questions render without immediate feedback
2. User selects answers for all questions (stored in `st.session_state["quiz_answers"][session_uid]`)
3. At the end, a "Submit Quiz" button calls `POST /evaluate-mastery`
4. After submission, show:
   - Score: X/Y correct (Z%)
   - Threshold: needed Z% to master
   - If mastered: success message + "Complete Session" unlocked
   - If not mastered: warning + "Review and Retake" button (clears answers)

**Changes to `render_questions()`:**

Replace the current function (lines 424-477) with a new implementation:

```python
def render_questions(quiz_data):
    """Render quiz questions in Submit All mode (no per-question feedback)."""
    st.subheader("Test Your Knowledge")
    session_uid = get_current_session_uid()

    # Initialize answer storage
    if session_uid not in st.session_state.get("quiz_answers", {}):
        st.session_state.setdefault("quiz_answers", {})[session_uid] = {
            "single_choice_questions": [None] * len(quiz_data.get("single_choice_questions", [])),
            "multiple_choice_questions": [[] for _ in quiz_data.get("multiple_choice_questions", [])],
            "true_false_questions": [None] * len(quiz_data.get("true_false_questions", [])),
            "short_answer_questions": [None] * len(quiz_data.get("short_answer_questions", [])),
        }

    answers = st.session_state["quiz_answers"][session_uid]
    q_num = 0

    # Single choice
    for i, q in enumerate(quiz_data.get("single_choice_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        selected = st.radio("Options", q["options"], key=f"sc_{session_uid}_{i}",
                           index=None, label_visibility="hidden")
        answers["single_choice_questions"][i] = selected

    # Multiple choice
    for i, q in enumerate(quiz_data.get("multiple_choice_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}** (Select all that apply)")
        selected = []
        for j, option in enumerate(q["options"]):
            if st.checkbox(option, key=f"mc_{session_uid}_{i}_{j}"):
                selected.append(option)
        answers["multiple_choice_questions"][i] = selected

    # True/False
    for i, q in enumerate(quiz_data.get("true_false_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        selected = st.radio("True or False?", ["True", "False"],
                           key=f"tf_{session_uid}_{i}", index=None, label_visibility="hidden")
        answers["true_false_questions"][i] = selected

    # Short answer
    for i, q in enumerate(quiz_data.get("short_answer_questions", [])):
        q_num += 1
        st.write(f"**{q_num}. {q['question']}**")
        user_answer = st.text_input("Your Answer", key=f"sa_{session_uid}_{i}",
                                     label_visibility="hidden")
        answers["short_answer_questions"][i] = user_answer if user_answer else None

    save_persistent_state()

    # Submit button
    mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})

    if mastery_info.get("is_mastered"):
        st.success(f"Mastery achieved! Score: {mastery_info['score']:.0f}% (threshold: {mastery_info['threshold']:.0f}%)")
    else:
        if st.button("Submit Quiz", type="primary", icon=":material/check_circle:"):
            result = evaluate_mastery(
                user_id=st.session_state.get("userId", ""),
                goal_id=st.session_state["selected_goal_id"],
                session_index=st.session_state["selected_session_id"],
                quiz_answers=answers,
            )
            if result:
                st.session_state.setdefault("mastery_status", {})[session_uid] = {
                    "score": result["score_percentage"],
                    "is_mastered": result["is_mastered"],
                    "threshold": result["threshold"],
                }
                save_persistent_state()
                st.rerun()
            else:
                st.error("Failed to evaluate quiz. Please try again.")

        if mastery_info.get("score") is not None and not mastery_info.get("is_mastered"):
            st.warning(f"Score: {mastery_info['score']:.0f}%. Need {mastery_info['threshold']:.0f}% to master this session.")
            if st.button("Retake Quiz", icon=":material/refresh:"):
                st.session_state["quiz_answers"].pop(session_uid, None)
                st.session_state["mastery_status"].pop(session_uid, None)
                save_persistent_state()
                st.rerun()
```

### 6B. Gate "Complete Session" behind mastery for sequential learners

**File:** `frontend/pages/knowledge_document.py`

In `render_session_details()` (line 98), modify the "Complete Session" button logic:

```python
# Read navigation mode from session data
navigation_mode = session_info.get("navigation_mode", "linear")
session_uid = get_current_session_uid()
mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})
is_mastered = mastery_info.get("is_mastered", False)

if navigation_mode == "linear":
    # Sequential learners: require mastery before completion
    complete_disabled = (
        complete_button_status
        or st.session_state["if_updating_learner_profile"]
        or not is_mastered
    )
    if not is_mastered and not complete_button_status:
        st.info("Pass the quiz to unlock session completion.")
else:
    # Global learners: existing behavior
    complete_disabled = complete_button_status or st.session_state["if_updating_learner_profile"]
```

Apply this logic to BOTH "Complete Session" buttons (top bar at line 129 and bottom at line 69).

---

## 7. Learning Path Page -- Navigation Gating and FSLSM Indicators

**File:** `frontend/pages/learning_path.py`

### 7A. Mastery Lock for sequential learners

New helper function:

```python
def _is_session_locked(goal, sid):
    """
    For linear navigation mode: session N is locked unless session N-1 is mastered.
    Session 0 is always unlocked.
    For free navigation mode: nothing is locked.
    """
    session = goal["learning_path"][sid]
    nav_mode = session.get("navigation_mode", "linear")

    if nav_mode == "free":
        return False
    if sid == 0:
        return False

    # Check if previous session is mastered
    prev_session = goal["learning_path"][sid - 1]
    prev_uid = f"{st.session_state['selected_goal_id']}-{sid - 1}"
    prev_mastery = st.session_state.get("mastery_status", {}).get(prev_uid, {})

    # Mastered if either the mastery_status state says so, or the session data says so
    return not prev_mastery.get("is_mastered", False) and not prev_session.get("is_mastered", False)
```

In `render_learning_sessions()`, modify the session card button area (around line 386):

```python
locked = _is_session_locked(goal, sid)

with col2:
    if locked:
        st.button("Locked", key=f"locked_{session['id']}",
                  use_container_width=True, disabled=True,
                  icon=":material/lock:")
        st.caption("Master the previous session first")
    elif not session["if_learned"]:
        # existing "Learning" button
        start_key = f"start_{session['id']}_{session['if_learned']}"
        if st.button("Learning", key=start_key, use_container_width=True,
                     type="primary", icon=":material/local_library:"):
            st.session_state["selected_session_id"] = sid
            st.session_state["selected_point_id"] = 0
            st.session_state["selected_page"] = "Knowledge Document"
            save_persistent_state()
            st.switch_page("pages/knowledge_document.py")
    else:
        # existing "Completed" button
        start_key = f"start_{session['id']}_{session['if_learned']}"
        if st.button("Completed", key=start_key, use_container_width=True,
                     type="secondary", icon=":material/done_outline:"):
            st.session_state["selected_session_id"] = sid
            st.session_state["selected_point_id"] = 0
            st.session_state["selected_page"] = "Knowledge Document"
            save_persistent_state()
            st.switch_page("pages/knowledge_document.py")
```

### 7B. Mastery score badge on session cards

Add inside each session card (after the expander, before the buttons):

```python
session_uid = f"{st.session_state['selected_goal_id']}-{sid}"
mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})
if mastery_info.get("score") is not None:
    score = mastery_info["score"]
    threshold = mastery_info.get("threshold", 70)
    if mastery_info.get("is_mastered"):
        st.markdown(f"**Mastery: {score:.0f}%** :white_check_mark:")
    else:
        st.markdown(f"**Quiz Score: {score:.0f}%** (need {threshold:.0f}%) :warning:")
```

### 7C. Checkpoint Challenges indicator (Active learners)

In session card, if `session.get("has_checkpoint_challenges")`:

```python
if session.get("has_checkpoint_challenges"):
    st.caption("Contains Checkpoint Challenges")
```

### 7D. Thinking Time buffer indicator (Reflective learners)

In session card, if `session.get("thinking_time_buffer_minutes", 0) > 0`:

```python
buffer = session.get("thinking_time_buffer_minutes", 0)
if buffer > 0:
    st.caption(f"Recommended reflection time: {buffer} min before next session")
```

### 7E. Module Map for visual learners

New function rendered at the top of the learning path (after `render_overall_information`, before session cards):

```python
def render_module_map(goal):
    """Visual map of the learning path for visual learners (fslsm_input <= -0.3)."""
    fslsm_dims = goal.get("learner_profile", {}).get(
        "learning_preferences", {}
    ).get("fslsm_dimensions", {})

    if fslsm_dims.get("fslsm_input", 0) > -0.3:
        return  # Only for visual learners

    st.write("#### Module Map")
    with st.container(border=True):
        # Simple visual representation using columns and arrows
        cols = st.columns(min(len(goal["learning_path"]), 5))
        for i, session in enumerate(goal["learning_path"]):
            col_idx = i % min(len(goal["learning_path"]), 5)
            with cols[col_idx]:
                if session.get("is_mastered") or session["if_learned"]:
                    color = "#5ecc6b"  # green
                    icon = ":material/check_circle:"
                elif _is_session_locked(goal, i) if 'navigation_mode' in session else False:
                    color = "#999"  # grey
                    icon = ":material/lock:"
                else:
                    color = "#fc7474"  # red
                    icon = ":material/radio_button_unchecked:"
                st.markdown(
                    f"<div style='text-align:center; padding:8px; border:2px solid {color}; "
                    f"border-radius:8px; margin:4px;'>"
                    f"<b>S{i+1}</b><br><small>{session['title'][:30]}</small></div>",
                    unsafe_allow_html=True
                )
```

Call in `render_learning_path()`:
```python
render_overall_information(goal)
render_module_map(goal)        # NEW
render_path_feedback_section(goal)
render_learning_sessions(goal)
```

### 7F. Narrative overview for verbal learners

New function:

```python
def render_narrative_overview(goal):
    """Narrative-style learning journey for verbal learners (fslsm_input >= 0.3)."""
    fslsm_dims = goal.get("learner_profile", {}).get(
        "learning_preferences", {}
    ).get("fslsm_dimensions", {})

    if fslsm_dims.get("fslsm_input", 0) < 0.3:
        return  # Only for verbal learners

    st.write("#### Your Learning Journey")
    with st.container(border=True):
        for i, session in enumerate(goal["learning_path"]):
            if session["if_learned"]:
                prefix = "You've completed"
                icon = ":material/done:"
            else:
                prefix = "Next, you'll explore"
                icon = ":material/arrow_forward:"
            st.write(f"{icon} **Chapter {i+1}:** {prefix} *{session['title']}* -- {session['abstract'][:120]}...")
```

Call alongside `render_module_map()`:
```python
render_overall_information(goal)
render_module_map(goal)
render_narrative_overview(goal)
render_path_feedback_section(goal)
render_learning_sessions(goal)
```

### 7G. Dual progress bars (completion vs mastery)

In `render_overall_information()` (line 181), replace the single progress section:

```python
st.write("#### Overall Progress")

mastered_count = sum(
    1 for i in range(total_sessions)
    if st.session_state.get("mastery_status", {}).get(
        f"{st.session_state['selected_goal_id']}-{i}", {}
    ).get("is_mastered", False)
    or goal["learning_path"][i].get("is_mastered", False)
)

col1, col2 = st.columns(2)
with col1:
    completion_pct = int((learned_sessions / total_sessions) * 100) if total_sessions else 0
    st.progress(completion_pct)
    st.write(f"{learned_sessions}/{total_sessions} sessions completed ({completion_pct}%)")
with col2:
    mastery_pct = int((mastered_count / total_sessions) * 100) if total_sessions else 0
    st.progress(mastery_pct)
    st.write(f"{mastered_count}/{total_sessions} sessions mastered ({mastery_pct}%)")
```

---

## Implementation Order

| Step | What | Files | Dependencies |
|------|------|-------|-------------|
| 1 | State management (5A, 5B) | `utils/state.py`, `utils/request_api.py` | Backend endpoints ready |
| 2 | Quiz Submit All model (6A) | `pages/knowledge_document.py` | Step 1 |
| 3 | Mastery-gated completion (6B) | `pages/knowledge_document.py` | Step 2 |
| 4 | Mastery lock navigation (7A) | `pages/learning_path.py` | Step 1 |
| 5 | Mastery badges (7B) | `pages/learning_path.py` | Step 1 |
| 6 | FSLSM indicators (7C, 7D) | `pages/learning_path.py` | Backend prompts ready |
| 7 | Module map (7E) | `pages/learning_path.py` | Step 4 |
| 8 | Narrative overview (7F) | `pages/learning_path.py` | None |
| 9 | Dual progress bars (7G) | `pages/learning_path.py` | Step 1 |

---

## Verification

1. **Sequential learner flow**: Select "Reflective Reader" persona (understanding=0.5 is actually global -- need to verify persona mappings). Use a sequential persona. Verify sessions 2+ are locked. Complete quiz in session 1 with passing score. Verify session 2 unlocks.
2. **Global learner flow**: Select "Conceptual Thinker" persona. Verify all sessions are navigable from the start.
3. **Active learner flow**: Select "Hands-on Explorer" persona. Verify "Checkpoint Challenges" indicator on session cards.
4. **Visual learner flow**: Select "Visual Learner" persona. Verify Module Map appears above session cards.
5. **Verbal learner flow**: Select "Reflective Reader" persona. Verify narrative overview appears.
6. **Quiz Submit All**: Start a session, scroll to quiz, answer all questions, click Submit. Verify score shown and mastery status updated.
7. **Mastery lock enforcement**: As sequential learner, try clicking locked session. Verify it is disabled.
8. **Retake quiz**: After failing mastery, click Retake. Verify answers cleared and can re-attempt.
