import streamlit as st
from collections import defaultdict
import pandas as pd
import re
import time

from utils.state import get_current_session_uid
from utils.request_api import get_app_config

def _get_selected_goal():
    """Return the currently selected goal dict from st.session_state.

    Supports common shapes:
      - goals: {<goal_id>: {...}}
      - goals: [{...}, {...}]
    """
    selected_goal_id = st.session_state.get("selected_goal_id")
    goals = st.session_state.get("goals")

    # Case A: goals is a dict keyed by id
    if isinstance(goals, dict):
        if selected_goal_id is None:
            # fallback: first goal in dict
            for _, g in goals.items():
                if isinstance(g, dict):
                    return g
            return None

        # Try direct key lookup (id might be str/int)
        if selected_goal_id in goals and isinstance(goals[selected_goal_id], dict):
            return goals[selected_goal_id]

        # Try string/int variants
        try:
            sid_str = str(selected_goal_id)
            if sid_str in goals and isinstance(goals[sid_str], dict):
                return goals[sid_str]
        except Exception:
            pass

        try:
            sid_int = int(selected_goal_id)
            if sid_int in goals and isinstance(goals[sid_int], dict):
                return goals[sid_int]
        except Exception:
            pass

        # Last resort: scan dict values by matching their "id"
        for g in goals.values():
            if isinstance(g, dict) and str(g.get("id")) == str(selected_goal_id):
                return g
        return None

    # Case B: goals is a list of goal dicts
    if isinstance(goals, list):
        if selected_goal_id is not None:
            for g in goals:
                if isinstance(g, dict) and str(g.get("id")) == str(selected_goal_id):
                    return g
        # fallback to first goal dict in list
        for g in goals:
            if isinstance(g, dict):
                return g
        return None

    return None

def render_dashboard():
    goal = _get_selected_goal()
    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded). Complete onboarding / load goals first.")
        return

    if not goal["learner_profile"]:
        st.warning("Please wait for the learning path to be scheduled to view the dashboard.")

    st.title("Learning Analytics")
    st.write("Track your learning progress and view learning insights here.")
    with st.container(border=True):
        render_learning_progress(goal)
    with st.container(border=True):
        render_skill_radar_chart(goal)
    with st.container(border=True):
        render_session_learning_timeseries(goal)
    with st.container(border=True):
        render_mastery_skills_timeseries(goal)


def render_learning_progress(goal):
    st.markdown("#### Learning Progress")
    st.write("View the learning progress for each session.")
    learner_profile = goal["learner_profile"]
    overall_progress = learner_profile["cognitive_status"]["overall_progress"]
    st.progress(overall_progress)
    st.write(f"Overall Progress: {overall_progress:.2f}%")

def render_skill_radar_chart(goal):
    import plotly.graph_objects as go

    st.markdown("#### Proficiency Levels for Different Skills")
    # st.write("View the skill radar chart for your learning progress.")
    learner_profile = goal["learner_profile"]
    mastered_skills = learner_profile["cognitive_status"]["mastered_skills"]
    in_progress_skills = learner_profile["cognitive_status"]["in_progress_skills"]
    skill_levels = get_app_config()["skill_levels"]
    level_map = defaultdict(lambda: 0, {name: i for i, name in enumerate(skill_levels)})
    mastered_skills = [{
        "name": skill_info["name"], 
        "required_level": skill_info["proficiency_level"], 
        "current_level": skill_info["proficiency_level"]} for skill_info in mastered_skills]
    in_progress_skills = [{
        "name": skill_info["name"], 
        "required_level": skill_info["required_proficiency_level"], 
        "current_level": skill_info["current_proficiency_level"]} for skill_info in in_progress_skills]
    skills = mastered_skills + in_progress_skills
    skill_names = [skill["name"] for skill in skills]
    current_levels = [level_map[skill["current_level"]] for skill in skills]
    required_levels = [level_map[skill["required_level"]] for skill in skills]
    st.write(f"You have mastered {len(mastered_skills)} skills and are currently learning {len(in_progress_skills)} skills.")

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=current_levels,
        theta=skill_names,
        fill='toself',
        name='Current Proficiency Level',
    ))
    fig.add_trace(go.Scatterpolar(
        r=required_levels,
        theta=skill_names,
        fill='toself',
        name='Required Proficiency Level',
        fillcolor='rgba(255, 192, 203, 0.3)',
        line=dict(color='rgba(255, 105, 97, 0.6)')
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, len(skill_levels) - 1],
                tickvals=list(range(len(skill_levels))),
                ticktext=[s.capitalize() for s in skill_levels],
                tickfont=dict(size=14)
            ),
            angularaxis=dict(  # Set font size for skill names (theta labels)
                tickfont=dict(size=18)
            )
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.1,
            xanchor="center",
            x=0.5,
            font=dict(size=18)
        ),
    )
    event = st.plotly_chart(fig, key="iris", on_select="rerun")


def render_session_learning_timeseries(goal):
    st.markdown("#### Session Learning Timeseries")
    st.write("View the learning progress over time.")

    # Always use the latest goal from session_state (passed-in goal can be stale across reruns)
    goal = _get_selected_goal()
    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded). Complete onboarding / load goals first.")
        return

    learning_path = goal.get("learning_path")

    # Accept common backend variants / partially-loaded states
    if learning_path is None:
        learning_path = goal.get("learning_plan")  # fallback key
    if isinstance(learning_path, dict):
        learning_path = learning_path.get("sessions") or learning_path.get("items") or []
    if learning_path is None:
        learning_path = []

    if not isinstance(learning_path, list):
        st.warning(f"Dashboard: learning_path is not a list (got {type(learning_path)}).")
        st.json({"learning_path": learning_path})
        return

    if len(learning_path) == 0:
        st.info("No learning sessions yet. Complete onboarding / generate a learning path first.")
        return

    session_learning_times = st.session_state.get("session_learning_times", {}) or {}
    selected_gid = st.session_state.get("selected_goal_id")

    session_rows = []
    for idx, session in enumerate(learning_path):
        if not isinstance(session, dict):
            continue

        sid = session.get("id", f"session-{idx}")
        if_learned = bool(session.get("if_learned", False))

        time_spent_min = 0.0
        if if_learned and selected_gid is not None:
            # Preferred: use the loop index as session index
            key = f"{selected_gid}-{idx}"
            times = session_learning_times.get(key)

            # Fallback: parse numeric id like "session_3" -> 2
            if times is None and isinstance(sid, str):
                m = re.search(r"\d+", sid)
                if m:
                    parsed_idx = max(int(m.group(0)) - 1, 0)
                    key2 = f"{selected_gid}-{parsed_idx}"
                    times = session_learning_times.get(key2)

            if isinstance(times, dict):
                start = times.get("start_time")
                end = times.get("end_time")
                if start is not None and end is not None:
                    try:
                        time_spent_min = max((end - start) / 60.0, 0.0)
                    except Exception:
                        time_spent_min = 0.0

        session_rows.append({"Session": sid, "Time": time_spent_min})

    if not session_rows:
        st.info("No valid session records to plot yet.")
        return

    df = pd.DataFrame(session_rows)
    st.bar_chart(df, x="Session", y="Time", stack=False)


def render_mastery_skills_timeseries(goal):
    st.markdown("#### Mastery Skills Timeseries")
    st.write("View the learning progress over time.")

    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded).")
        return

    goal_id = goal.get("id")

    # learned_skills_history can be missing or not keyed by goal id yet
    learned_skills_history = st.session_state.get("learned_skills_history", {})

    history_for_goal = None

    # Case A: dict keyed by goal id
    if isinstance(learned_skills_history, dict) and goal_id is not None:
        history_for_goal = learned_skills_history.get(goal_id)
        if history_for_goal is None:
            history_for_goal = learned_skills_history.get(str(goal_id))
        if history_for_goal is None:
            try:
                history_for_goal = learned_skills_history.get(int(goal_id))
            except Exception:
                pass

    # Case B: already a list (single-goal mode)
    if history_for_goal is None and isinstance(learned_skills_history, list):
        history_for_goal = learned_skills_history

    # Normalize
    if history_for_goal is None:
        history_for_goal = []

    if not isinstance(history_for_goal, list) or len(history_for_goal) == 0:
        st.info("No learned skills history yet. Generate/complete sessions to populate mastery trends.")
        return

    time_values = [i * 10 for i in range(len(history_for_goal))]
    chart_data = pd.DataFrame({
        "Time": time_values,
        "Mastery Rate": history_for_goal,
    })

    st.line_chart(chart_data, x="Time", y="Mastery Rate")

render_dashboard()
