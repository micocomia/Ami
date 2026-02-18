import time
import math
import streamlit as st
from components.skill_info import render_skill_info
from utils.request_api import (
    schedule_learning_path_agentic,
    reschedule_learning_path,
    adapt_learning_path,
    get_app_config,
)
from components.navigation import render_navigation
from utils.state import save_persistent_state

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

def render_learning_path():
    if not st.session_state.get("if_complete_onboarding"):
        st.switch_page("pages/onboarding.py")

    goal = _get_selected_goal()
    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded). Go to Onboarding / Goal Management first.")
        return
    save_persistent_state()
    if not goal["learning_goal"] or not st.session_state["learner_information"]:
        st.switch_page("pages/onboarding.py")
    else:
        if not goal["skill_gaps"]:
            st.switch_page("pages/skill_gap.py")

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

        with st.spinner("Generating learning path (with retrieval, evaluation & auto-refinement)..."):
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

        goal["learning_path"] = learning_path
        goal["plan_agent_metadata"] = agent_metadata
        try:
            save_persistent_state()
        except Exception:
            pass
        st.toast("Successfully scheduled learning path!")
        st.rerun()

    else:
        render_overall_information(goal)
        render_module_map(goal)
        render_narrative_overview(goal)
        render_plan_quality_section(goal)
        render_adaptation_section(goal)
        render_learning_sessions(goal)


def render_overall_information(goal):
    with st.container(border=True):
        st.write("#### Current Goal")
        st.text_area("In-progress Goal", value=goal["learning_goal"], disabled=True, help="Change this in the Goal Management section.")
        learned_sessions = sum(1 for s in goal["learning_path"] if s["if_learned"])
        total_sessions = len(goal["learning_path"])
        if total_sessions == 0:
            st.warning("No learning sessions found.")
            return

        # Mastery count
        mastered_count = sum(
            1 for i in range(total_sessions)
            if st.session_state.get("mastery_status", {}).get(
                f"{st.session_state['selected_goal_id']}-{i}", {}
            ).get("is_mastered", False)
            or goal["learning_path"][i].get("is_mastered", False)
        )

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

def _is_session_locked(goal, sid):
    """Check if a session is locked due to mastery lock (sequential learners).

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

    return not prev_mastery.get("is_mastered", False) and not prev_session.get("is_mastered", False)


def render_module_map(goal):
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
                elif _is_session_locked(goal, i):
                    color = "#999"
                else:
                    color = "#fc7474"
                st.markdown(
                    f"<div style='text-align:center; padding:8px; border:2px solid {color}; "
                    f"border-radius:8px; margin:4px;'>"
                    f"<b>S{i+1}</b><br><small>{session['title'][:30]}</small></div>",
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
    with st.container(border=True):
        for i, session in enumerate(goal["learning_path"]):
            if session["if_learned"]:
                prefix = "You've completed"
            else:
                prefix = "Next, you'll explore"
            abstract_preview = session["abstract"][:120]
            st.write(f"**Chapter {i+1}:** {prefix} *{session['title']}* -- {abstract_preview}...")


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
                    if isinstance(val, str):
                        display = val[:120] + "..." if len(val) > 120 else val
                    else:
                        display = str(val)
                    st.caption(display)

        st.caption(f"Refinement iterations: {iterations}")


def render_adaptation_section(goal):
    """Show adaptation suggestion banner when preferences change significantly."""
    goal_id = st.session_state.get("selected_goal_id")
    user_id = st.session_state.get("userId", "")

    # Check for pending adaptation suggestion (set by mastery evaluation or preference change)
    adaptation_key = f"adaptation_suggested_{goal_id}"
    if st.session_state.get(adaptation_key):
        st.warning("Your learning preferences or quiz results suggest your learning path may need adjustment.")
        if st.button("Adapt Learning Path", type="primary", key=f"adapt_btn_{goal_id}"):
            with st.spinner("Analyzing changes and adapting your learning path..."):
                result = adapt_learning_path(
                    user_id=user_id,
                    goal_id=goal_id,
                    new_learner_profile=goal.get("learner_profile", {}),
                )
            if result and result.get("learning_path"):
                agent_meta = result.get("agent_metadata", {})
                decision = agent_meta.get("decision", {})
                action = decision.get("action", "keep")
                reason = decision.get("reason", "")

                if action == "keep":
                    st.info("Your current plan is still on track.")
                elif action == "adjust_future":
                    goal["learning_path"] = result["learning_path"]
                    goal["plan_agent_metadata"] = agent_meta
                    st.success(f"Future sessions have been adjusted. {reason}")
                elif action == "regenerate":
                    goal["learning_path"] = result["learning_path"]
                    goal["plan_agent_metadata"] = agent_meta
                    st.success(f"Your learning path has been regenerated. {reason}")

                st.session_state[adaptation_key] = False
                save_persistent_state()
                st.rerun()
            else:
                st.error("Failed to adapt learning path.")


def render_learning_sessions(goal):
    st.write("#### 📖 Learning Sessions")
    total_sessions = len(goal["learning_path"])
    with st.expander("Re-schedule Learning Path", expanded=False):
        st.info("Customize your learning path by re-scheduling sessions or marking them as complete.")
        expected_session_count = st.number_input("Expected Sessions", min_value=0, max_value=10, value=total_sessions)
        st.session_state["expected_session_count"] = expected_session_count
        try:
            save_persistent_state()
        except Exception:
            pass
        if st.button("Re-schedule Learning Path", type="primary"):
            st.session_state["if_rescheduling_learning_path"] = True
            try:
                save_persistent_state()
            except Exception:
                pass
            st.rerun()
        if st.session_state.get("if_rescheduling_learning_path"):
            with st.spinner('Re-scheduling Learning Path ...'):
                result = reschedule_learning_path(goal["learning_path"], goal["learner_profile"], expected_session_count)
                _store_agent_reasoning(result, 'reschedule_learning_path')
                goal["learning_path"] = result.get('learning_path', result) if isinstance(result, dict) else result
                st.session_state["if_rescheduling_learning_path"] = False
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.toast("🎉 Successfully re-schedule learning path!")
                st.rerun()
    save_persistent_state()
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
                session_uid = f"{st.session_state['selected_goal_id']}-{sid}"
                mastery_info = st.session_state.get("mastery_status", {}).get(session_uid, {})
                if mastery_info.get("score") is not None:
                    score = mastery_info["score"]
                    threshold = mastery_info.get("threshold", 70)
                    if mastery_info.get("is_mastered"):
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

                locked = _is_session_locked(goal, sid)

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