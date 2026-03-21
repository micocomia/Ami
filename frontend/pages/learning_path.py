import math
import streamlit as st
from components.skill_info import render_skill_info
from utils.request_api import (
    schedule_learning_path_agentic,
    adapt_learning_path,
    get_app_config,
    get_goal_runtime_state,
    post_session_activity,
    update_goal,
)
from utils.state import load_persistent_state, save_persistent_state

def _get_selected_goal():
    """Return the currently selected goal dict from st.session_state.
    Supports:
      - goals as dict keyed by goal_id
      - goals as list of goal dicts
    """
    selected_goal_id = st.session_state.get("selected_goal_id")
    goals = st.session_state.get("goals")

    if isinstance(goals, dict):
        if selected_goal_id is not None:
            if selected_goal_id in goals and isinstance(goals[selected_goal_id], dict):
                return goals[selected_goal_id]
            if str(selected_goal_id) in goals and isinstance(goals[str(selected_goal_id)], dict):
                return goals[str(selected_goal_id)]
            try:
                sid_int = int(selected_goal_id)
                if sid_int in goals and isinstance(goals[sid_int], dict):
                    return goals[sid_int]
            except Exception:
                pass
            for g in goals.values():
                if isinstance(g, dict) and str(g.get("id")) == str(selected_goal_id):
                    return g
        for g in goals.values():
            if isinstance(g, dict):
                return g
        return None

    if isinstance(goals, list):
        if selected_goal_id is not None:
            for g in goals:
                if isinstance(g, dict) and str(g.get("id")) == str(selected_goal_id):
                    return g
        for g in goals:
            if isinstance(g, dict):
                return g
        return None

    return None


def _store_agent_reasoning(result, context: str = ""):
    """Store any agent reasoning/trace returned by backend into Streamlit session_state.

    This enables the main sidebar 'Agent reasoning' panel (or any page) to display it.
    Safe for string/dict/list responses.
    """
    if result is None:
        return

    payload = None
    raw = None

    if isinstance(result, dict):
        raw = result
        # Common keys teams use
        for k in ("reasoning", "rationale", "explanation", "agent_reasoning"):
            v = result.get(k)
            if v:
                payload = v
                break

        # Fallback: trace-like structures
        if payload is None:
            for k in ("trace", "traces", "debug_trace", "steps", "chain", "log"):
                v = result.get(k)
                if v:
                    payload = v
                    break

    # If backend returns list/string directly
    elif isinstance(result, (list, str)):
        payload = result

    if payload is not None:
        st.session_state["agent_reasoning"] = payload
        if context:
            st.session_state["agent_reasoning_context"] = context
        if raw is not None:
            st.session_state["agent_reasoning_raw_response"] = raw


def _get_runtime_state(goal_id):
    user_id = st.session_state.get("userId")
    if not user_id or goal_id is None:
        return None
    runtime = get_goal_runtime_state(user_id, goal_id)
    if runtime:
        st.session_state[f"goal_runtime_state_{goal_id}"] = runtime
    return runtime or st.session_state.get(f"goal_runtime_state_{goal_id}")


def _auto_adapt_if_needed(goal, runtime_state=None):
    adaptation = (runtime_state or {}).get("adaptation", {})
    if not adaptation.get("suggested", False):
        return
    user_id = st.session_state.get("userId")
    goal_id = goal.get("id")
    if not user_id or goal_id is None:
        return
    inflight_key = f"auto_adapt_inflight_{goal_id}"
    if st.session_state.get(inflight_key):
        return
    st.session_state[inflight_key] = True
    try:
        with st.spinner("Adapting your learning path based on recent progress..."):
            result = adapt_learning_path(user_id=user_id, goal_id=goal_id)
    finally:
        st.session_state[inflight_key] = False
    if not isinstance(result, dict):
        return
    _store_agent_reasoning(result, "adapt_learning_path")
    adaptation_status = (result.get("adaptation") or {}).get("status")
    if adaptation_status == "applied" and result.get("learning_path"):
        persisted = update_goal(
            user_id,
            goal_id,
            {"learning_path": result["learning_path"], "plan_agent_metadata": result.get("agent_metadata", {})},
        )
        if persisted is not None:
            goal["learning_path"] = result["learning_path"]
            goal["plan_agent_metadata"] = result.get("agent_metadata", {})
        load_persistent_state()
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("Learning path adapted automatically.")
        st.rerun()

def render_learning_path():
    goal = _get_selected_goal()
    has_existing_learning_path = isinstance(goal, dict) and bool(goal.get("learning_path"))
    onboarding_complete = st.session_state.get("if_complete_onboarding")

    if not onboarding_complete and not has_existing_learning_path:
        st.switch_page("pages/onboarding.py")

    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded). Go to Onboarding / Goal Management first.")
        return
    runtime_state = _get_runtime_state(goal.get("id"))
    save_persistent_state()
    if not has_existing_learning_path:
        if not goal.get("learning_goal"):
            st.switch_page("pages/goal_management.py" if onboarding_complete else "pages/onboarding.py")
        if not goal.get("skill_gaps"):
            st.switch_page("pages/goal_management.py" if onboarding_complete else "pages/skill_gap.py")
        if not goal.get("learner_profile"):
            st.switch_page("pages/goal_management.py" if onboarding_complete else "pages/onboarding.py")

    st.title("Learning Path")
    st.write("Track your learning progress through the sessions below.")

    st.markdown("""
        <style>
        .card-header {
            color: #333;
            font-weight: bold;
            margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if not goal.get("learning_path"):

        goal_id = goal.get("id", st.session_state.get("selected_goal_id"))
        attempt_key = f"learning_path_schedule_attempted_{goal_id}"

        # Avoid infinite rerun loops if scheduling fails
        if st.session_state.get(attempt_key):
            st.warning("Learning path is not available yet.")
            if st.button("Retry scheduling learning path", type="primary"):
                st.session_state[attempt_key] = False
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.rerun()
            return

        with st.spinner("Generating learning path (with evaluation & auto-refinement)..."):
            st.session_state[attempt_key] = True

            result = schedule_learning_path_agentic(
                learner_profile=goal.get("learner_profile"),
                session_count=get_app_config()["default_session_count"],
            )

        _store_agent_reasoning(result, "schedule_learning_path_agentic")

        # Backend returns {learning_path: [...], agent_metadata: {...}}
        if isinstance(result, dict):
            if "detail" in result and not result.get("learning_path"):
                st.error("Backend rejected the schedule request (422).")
                st.json(result)
                return
            learning_path = result.get("learning_path")
            agent_metadata = result.get("agent_metadata", {})
        else:
            learning_path = result
            agent_metadata = {}

        if not learning_path:
            st.error("Scheduling returned an empty learning path.")
            return

        persisted = update_goal(
            st.session_state.get("userId"),
            goal.get("id"),
            {"learning_path": learning_path, "plan_agent_metadata": agent_metadata},
        )
        if persisted is None:
            st.error("Failed to save learning path to backend. Please retry.")
            return
        goal["learning_path"] = learning_path
        goal["plan_agent_metadata"] = agent_metadata
        load_persistent_state()
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("Successfully scheduled learning path!")
        st.rerun()

    else:
        adaptation = (runtime_state or {}).get("adaptation", {})
        if adaptation.get("suggested", False):
            st.info("Learning path update in progress. This can take up to 2 minutes.")
        _auto_adapt_if_needed(goal, runtime_state)
        render_overall_information(goal, runtime_state)
        render_plan_quality_section(goal)
        render_module_map(goal, runtime_state)
        render_narrative_overview(goal)
        render_learning_sessions(goal, runtime_state)


def render_overall_information(goal, runtime_state=None):
    with st.container(border=True):
        st.write("#### Current Goal")
        st.text_area("In-progress Goal", value=goal["learning_goal"], disabled=True, help="Change this in the Goal Management section.")
        learned_sessions = sum(1 for s in goal["learning_path"] if s["if_learned"])
        total_sessions = len(goal["learning_path"])
        if total_sessions == 0:
            st.warning("No learning sessions found.")
            return

        # Mastery count
        runtime_sessions = (runtime_state or {}).get("sessions", [])
        if runtime_sessions:
            mastered_count = sum(1 for session in runtime_sessions if session.get("is_mastered"))
        else:
            mastered_count = sum(1 for session in goal["learning_path"] if session.get("is_mastered"))

        st.write("#### Overall Progress")
        col1, col2 = st.columns(2)
        with col1:
            completion_pct = int((learned_sessions / total_sessions) * 100)
            st.progress(completion_pct)
            st.write(f"{learned_sessions}/{total_sessions} sessions completed ({completion_pct}%)")
        with col2:
            mastery_pct = int((mastered_count / total_sessions) * 100)
            st.progress(mastery_pct)
            st.write(f"{mastered_count}/{total_sessions} sessions mastered ({mastery_pct}%)")

        if learned_sessions == total_sessions:
            st.success("Congratulations! All sessions are complete.")
            st.balloons()
        else:
            st.info("Keep going! You're making great progress.")
        with st.expander("View Skill Details", expanded=False):
            render_skill_info(goal["learner_profile"])

def _is_session_locked(goal, sid, runtime_state=None):
    runtime_sessions = (runtime_state or {}).get("sessions", [])
    if sid < len(runtime_sessions):
        return bool(runtime_sessions[sid].get("is_locked", False))
    session = goal["learning_path"][sid]
    nav_mode = session.get("navigation_mode", "linear")
    return nav_mode != "free" and sid > 0 and not bool(goal["learning_path"][sid - 1].get("is_mastered", False))


def render_module_map(goal, runtime_state=None):
    """Visual map of the learning path for visual learners (fslsm_input <= -0.3)."""
    fslsm_dims = goal.get("learner_profile", {}).get(
        "learning_preferences", {}
    ).get("fslsm_dimensions", {})

    if fslsm_dims.get("fslsm_input", 0) > -0.3:
        return  # Only for visual learners

    st.write("#### Module Map")
    with st.container(border=True):
        num_sessions = len(goal["learning_path"])
        cols_per_row = min(num_sessions, 5)
        cols = st.columns(cols_per_row)
        for i, session in enumerate(goal["learning_path"]):
            col_idx = i % cols_per_row
            with cols[col_idx]:
                if session.get("is_mastered") or session["if_learned"]:
                    color = "#5ecc6b"
                elif _is_session_locked(goal, i, runtime_state):
                    color = "#999"
                else:
                    color = "#fc7474"
                st.markdown(
                    f"<div style='text-align:center; padding:8px; border:2px solid {color}; "
                    f"border-radius:8px; margin:4px;'>"
                    f"<b>S{i+1}</b><br><small>{session['title']}</small></div>",
                    unsafe_allow_html=True
                )


def render_narrative_overview(goal):
    """Narrative-style learning journey for verbal learners (fslsm_input >= 0.3)."""
    fslsm_dims = goal.get("learner_profile", {}).get(
        "learning_preferences", {}
    ).get("fslsm_dimensions", {})

    if fslsm_dims.get("fslsm_input", 0) < 0.3:
        return  # Only for verbal learners

    st.write("#### Your Learning Journey")
    first_upcoming_idx = next((i for i, session in enumerate(goal["learning_path"]) if not session["if_learned"]), None)
    with st.container(border=True):
        for i, session in enumerate(goal["learning_path"]):
            if session["if_learned"]:
                prefix = "You've completed"
            elif first_upcoming_idx is not None and i == first_upcoming_idx:
                prefix = "First, you'll explore"
            else:
                prefix = "Next, you'll explore"
            st.write(f"**Chapter {i+1}:** {prefix} *{session['title']}* -- {session['abstract']}")


def render_plan_quality_section(goal):
    """Display the agent's auto-evaluation quality results (read-only)."""
    metadata = goal.get("plan_agent_metadata", {})
    if not metadata:
        return

    evaluation = metadata.get("evaluation", {})
    iterations = metadata.get("refinement_iterations", 1)
    feedback_summary = evaluation.get("feedback_summary", {})

    with st.expander("Plan Quality (Auto-Evaluated)", expanded=False):
        # Quality status
        passed = evaluation.get("pass", True)
        if passed:
            st.success(f"Plan Quality: PASS (after {iterations} iteration{'s' if iterations > 1 else ''})")
        else:
            issues = evaluation.get("issues", [])
            st.warning(f"Plan Quality: NEEDS REVIEW ({len(issues)} issues, {iterations} iterations)")
            for issue in issues:
                st.write(f"- {issue}")

        # Feedback summary
        if feedback_summary:
            fb_cols = st.columns(len(feedback_summary))
            for i, (key, val) in enumerate(feedback_summary.items()):
                with fb_cols[i]:
                    st.write(f"**{key.title()}**")
                    display = val if isinstance(val, str) else str(val)
                    st.caption(display)

        st.caption(f"Refinement iterations: {iterations}")


def render_learning_sessions(goal, runtime_state=None):
    st.write("#### 📖 Learning Sessions")
    save_persistent_state()
    runtime_sessions = (runtime_state or {}).get("sessions", [])
    columns_spec = 2
    num_columns = math.ceil(len(goal["learning_path"]) / columns_spec)
    columns_list = [st.columns(columns_spec, gap="large") for _ in range(num_columns)]
    for sid, session in enumerate(goal["learning_path"]):
        session_column = columns_list[sid // columns_spec]
        with session_column[sid % columns_spec]:
            with st.container(border=True):
                text_color = "#5ecc6b" if session["if_learned"] else "#fc7474"

                st.markdown(f"<div class='card'><div class='card-header' style='color: {text_color};'>{sid+1}: {session['title']}</div>", unsafe_allow_html=True)

                with st.expander("View Session Details", expanded=False):
                    st.info(session["abstract"])
                    st.write("**Associated Skills & Desired Proficiency:**")
                    for skill_outcome in session["desired_outcome_when_completed"]:
                        st.write(f"- {skill_outcome['name']} (`{skill_outcome['level']}`)")

                    # Sequence hint from perception dimension
                    seq_hint = session.get("session_sequence_hint")
                    if seq_hint == "application-first":
                        st.caption("Content order: Application -> Example -> Theory")
                    elif seq_hint == "theory-first":
                        st.caption("Content order: Theory-first / Conceptual exploration")

                # Mastery score badge
                runtime_session = runtime_sessions[sid] if sid < len(runtime_sessions) else {}
                score = runtime_session.get("mastery_score", session.get("mastery_score"))
                threshold = runtime_session.get("mastery_threshold", session.get("mastery_threshold", 70))
                is_mastered = runtime_session.get("is_mastered", session.get("is_mastered", False))
                if score is not None:
                    if is_mastered:
                        st.markdown(f"**Mastery: {score:.0f}%** :white_check_mark:")
                    else:
                        st.markdown(f"**Quiz Score: {score:.0f}%** (need {threshold:.0f}%) :warning:")

                # FSLSM indicators
                if session.get("has_checkpoint_challenges"):
                    st.caption("Contains Checkpoint Challenges")
                buffer = session.get("thinking_time_buffer_minutes", 0)
                if buffer > 0:
                    st.caption(f"Recommended reflection time: {buffer} min before next session")

                col1, col2 = st.columns([5, 3])
                with col1:
                    if_learned_key = f"if_learned_{session['id']}"
                    old_if_learned = session["if_learned"]
                    session_status_hint = "Keep Learning" if not session["if_learned"] else "Completed"
                    session_if_learned = st.toggle(session_status_hint, value=session["if_learned"], key=if_learned_key, disabled=True)
                    goal["learning_path"][sid]["if_learned"] = session_if_learned
                    save_persistent_state()
                    if session_if_learned != old_if_learned:
                        st.rerun()

                locked = bool(runtime_session.get("is_locked")) if runtime_session else _is_session_locked(goal, sid)

                with col2:
                    if locked:
                        st.button(
                            "Locked", key=f"locked_{session['id']}",
                            use_container_width=True, disabled=True,
                            icon=":material/lock:",
                        )
                        st.caption("Master the previous session first")
                    elif not session["if_learned"]:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Learning", key=start_key, use_container_width=True, type="primary", icon=":material/local_library:"):
                            user_id = st.session_state.get("userId")
                            goal_id = goal.get("id")
                            if user_id is not None and goal_id is not None:
                                post_session_activity(user_id, goal_id, sid, "start")
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Knowledge Document"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")
                    else:
                        start_key = f"start_{session['id']}_{session['if_learned']}"
                        if st.button("Completed", key=start_key, use_container_width=True, type="secondary", icon=":material/done_outline:"):
                            st.session_state["selected_session_id"] = sid
                            st.session_state["selected_point_id"] = 0
                            st.session_state["selected_page"] = "Knowledge Document"
                            save_persistent_state()
                            st.switch_page("pages/knowledge_document.py")


render_learning_path()
