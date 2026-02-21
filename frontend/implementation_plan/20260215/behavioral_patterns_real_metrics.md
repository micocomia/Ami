# Behavioral Patterns: Frontend Real Metrics Display

## Context

The learner profile's behavioral patterns section currently displays LLM-hallucinated text. A new backend endpoint `GET /behavioral-metrics/{user_id}?goal_id=X` (see `backend/implementation_plan/20260214/behavioral_patterns_real_metrics.md`) computes real metrics from stored `session_learning_times` and `learned_skills_history`. This plan updates the frontend to call that endpoint and display the computed metrics.

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `frontend/utils/request_api.py` | Modify | Add `get_behavioral_metrics()` function |
| `frontend/pages/learner_profile.py` | Modify | Rewrite `render_behavioral_patterns()` (lines 157-167) |

---

## Implementation Plan

### 1. Add `get_behavioral_metrics()` in `frontend/utils/request_api.py`

Add near the other GET utility functions (e.g., near `get_app_config`):

```python
def get_behavioral_metrics(user_id, goal_id=None):
    """Fetch computed behavioral metrics from the backend."""
    url = f"{backend_endpoint}behavioral-metrics/{user_id}"
    if goal_id is not None:
        url += f"?goal_id={goal_id}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None
```

### 2. Rewrite `render_behavioral_patterns()` in `frontend/pages/learner_profile.py`

Replace the current function (lines 157-167) which displays `learner_profile['behavioral_patterns']` strings.

**Add import** at top of file:
```python
from utils.request_api import ..., get_behavioral_metrics
```

**New function:**

```python
def render_behavioral_patterns(goal):
    st.markdown("#### Behavioral Patterns")

    # Fetch real metrics from backend
    user_id = st.session_state.get("userId")
    goal_id = None
    if isinstance(goal, dict) and "id" in goal:
        goal_id = goal["id"]
    metrics = get_behavioral_metrics(user_id, goal_id) if user_id else None

    if metrics is None:
        # Fallback to LLM-generated text if endpoint unavailable
        learner_profile = goal["learner_profile"]
        bp = learner_profile.get("behavioral_patterns", {})
        st.write("**System Usage Frequency:**")
        st.info(bp.get("system_usage_frequency", "N/A"))
        st.write("**Session Duration and Engagement:**")
        st.info(bp.get("session_duration_engagement", "N/A"))
        st.write("**Motivational Triggers:**")
        st.info(bp.get("motivational_triggers", "N/A"))
        st.write("**Additional Notes:**")
        st.info(bp.get("additional_notes", "N/A"))
        return

    # --- Session Completion ---
    st.write("**Session Completion:**")
    total_in_path = metrics.get("total_sessions_in_path", 0)
    sessions_learned = metrics.get("sessions_learned", 0)
    if total_in_path > 0:
        st.progress(sessions_learned / total_in_path)
        st.caption(f"{sessions_learned} of {total_in_path} sessions completed")
    else:
        st.info("No learning path generated yet.")

    # --- Session Duration & Engagement ---
    st.write("**Session Duration & Engagement:**")
    sessions_completed = metrics.get("sessions_completed", 0)
    if sessions_completed > 0:
        avg_min = metrics.get("avg_session_duration_sec", 0) / 60.0
        total_min = metrics.get("total_learning_time_sec", 0) / 60.0
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sessions Completed", sessions_completed)
        with col2:
            st.metric("Avg Duration", f"{avg_min:.1f} min")
        with col3:
            st.metric("Total Learning Time", f"{total_min:.1f} min")
    else:
        st.info("No completed sessions yet. Complete a learning session to see engagement metrics.")

    # --- Motivational Triggers ---
    st.write("**Motivational Triggers:**")
    trigger_count = metrics.get("motivational_triggers_count", 0)
    if sessions_completed > 0:
        st.caption(f"{trigger_count} motivational trigger(s) received across all sessions")
    else:
        st.info("No data yet.")

    # --- Mastery Progress ---
    st.write("**Mastery Progress:**")
    latest_mastery = metrics.get("latest_mastery_rate")
    mastery_history = metrics.get("mastery_history", [])
    if latest_mastery is not None:
        st.progress(min(float(latest_mastery), 1.0))
        st.caption(f"Latest mastery rate: {latest_mastery:.1%} (sampled {len(mastery_history)} time(s))")
    else:
        st.info("No mastery data yet. Study sessions to see your mastery trend.")
```

**Key design decisions:**
- Falls back to LLM-generated text if the backend endpoint is unavailable (graceful degradation)
- Converts seconds to minutes for display
- Reuses `st.metric()` for the three engagement cards (consistent with Streamlit patterns)
- Uses `st.progress()` for session completion and mastery (consistent with the existing cognitive status display in the same page)

---

## Verification

1. Start the backend and frontend
2. Navigate to My Profile with a fresh profile — should show "No data yet" messages for duration/triggers/mastery and "0 of N sessions completed" for completion
3. Complete a learning session, return to My Profile — should show real session count, duration, total time
4. Complete a session lasting >3 minutes — motivational trigger count should be >0
5. Switch between goals via Goal Management — metrics should reflect the selected goal only
6. Stop the backend, reload My Profile — should fall back to LLM-generated behavioral patterns text
