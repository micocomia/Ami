import streamlit as st
import pandas as pd

from utils.request_api import get_app_config, get_bias_audit_history, get_dashboard_metrics, list_goals
from utils.state import get_selected_goal


def _get_active_goals():
    """Return all non-deleted goals from session state."""
    goals = st.session_state.get("goals", [])
    return [g for g in goals if isinstance(g, dict) and not g.get("is_deleted", False)]


def render_dashboard():
    goal = get_selected_goal()
    if not isinstance(goal, dict):
        st.info("No goal selected yet (or goals data not loaded). Complete onboarding / load goals first.")
        return

    user_id = st.session_state.get("userId")

    if user_id:
        fresh_goals = list_goals(user_id)
        if fresh_goals:
            st.session_state["goals"] = fresh_goals

    st.title("Learning Analytics")
    st.write("Track your learning progress and view learning insights here.")

    # Goal selector at the top — controls the entire dashboard
    active_goals = _get_active_goals()
    if not active_goals:
        st.warning("No goals available yet.")
        return

    goal_options = {}
    for g in active_goals:
        raw_name = (
            g.get("goal_display_name")
            or g.get("learner_profile", {}).get("goal_display_name", "")
            or g.get("learning_goal", g.get("goal", f"Goal {g.get('id', '?')}"))
        )
        goal_options[raw_name] = g

    # Default to currently selected goal
    current_goal_name = (
        goal.get("goal_display_name")
        or goal.get("learner_profile", {}).get("goal_display_name", "")
        or goal.get("learning_goal", goal.get("goal", ""))
    )
    default_index = 0
    option_keys = list(goal_options.keys())
    if current_goal_name in option_keys:
        default_index = option_keys.index(current_goal_name)

    selected_label = st.selectbox(
        "Select a learning goal",
        options=option_keys,
        index=default_index,
        key="dashboard_goal_selector",
    )
    selected_goal = goal_options[selected_label]
    selected_goal_id = selected_goal.get("id")

    # Fetch metrics for the selected goal
    metrics = get_dashboard_metrics(user_id, selected_goal_id) if user_id and selected_goal_id is not None else None
    if not metrics:
        st.warning("Analytics are not available yet for this goal.")
        return

    st.markdown(f"**Showing analytics for: {selected_label}**")

    with st.container(border=True):
        render_learning_progress(metrics)
    with st.container(border=True):
        render_skill_radar_chart(metrics, goal_name=selected_label)
    with st.container(border=True):
        render_session_learning_timeseries(metrics)
    with st.container(border=True):
        render_mastery_skills_timeseries(metrics)
    with st.container(border=True):
        render_bias_ethics_review(user_id, selected_goal_id)


def render_learning_progress(metrics):
    st.markdown("#### Learning Progress")
    st.write("View the learning progress for each session.")
    overall_progress = float(metrics.get("overall_progress", 0.0) or 0.0)
    st.progress(max(min(int(overall_progress), 100), 0))
    st.write(f"Overall Progress: {overall_progress:.2f}%")


def render_skill_radar_chart(metrics, goal_name=""):
    import plotly.graph_objects as go

    title = "Proficiency Levels for Different Skills"
    if goal_name:
        title = f"Proficiency Levels for Different Skills — {goal_name}"
    st.markdown(f"#### {title}")

    skill_radar = metrics.get("skill_radar", {})
    skill_names = [name.title() for name in skill_radar.get("labels", [])]
    current_levels = skill_radar.get("current_levels", [])
    required_levels = skill_radar.get("required_levels", [])
    skill_levels = skill_radar.get("skill_levels") or get_app_config()["skill_levels"]

    if not skill_names:
        st.info("No skill proficiency data is available yet.")
        return

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
                range=[0, max(len(skill_levels) - 1, 0)],
                tickvals=list(range(len(skill_levels))),
                ticktext=[s.capitalize() for s in skill_levels],
                tickfont=dict(size=14)
            ),
            angularaxis=dict(tickfont=dict(size=18))
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
    st.plotly_chart(fig, key="skill_radar_chart", on_select="rerun")


def render_session_learning_timeseries(metrics):
    st.markdown("#### Session Learning Timeseries")
    st.write("View the learning progress over time.")
    series = metrics.get("session_time_series", [])
    if not series:
        st.info("No learning sessions yet. Complete onboarding / generate a learning path first.")
        return
    df = pd.DataFrame([
        {
            "Session": item.get("session_id", ""),
            "Time": float(item.get("time_spent_min", 0.0) or 0.0),
        }
        for item in series
    ])
    st.bar_chart(df, x="Session", y="Time", stack=False)


def render_mastery_skills_timeseries(metrics):
    st.markdown("#### Mastery Skills Timeseries")
    st.write("View the learning progress over time.")
    series = metrics.get("mastery_time_series", [])
    if not series:
        st.info("No learned skills history yet. Generate/complete sessions to populate mastery trends.")
        return
    chart_data = pd.DataFrame({
        "Time": [item.get("sample_index", idx) * 10 for idx, item in enumerate(series)],
        "Mastery Rate": [float(item.get("mastery_rate", 0.0) or 0.0) for item in series],
    })
    st.line_chart(chart_data, x="Time", y="Mastery Rate")


def render_bias_ethics_review(user_id, goal_id):
    st.markdown("#### Bias & Ethics Review")
    st.write("Track bias audit results across your learning journey.")

    data = get_bias_audit_history(user_id, goal_id) if user_id else None
    if not data or not data.get("entries"):
        st.info("No bias audits recorded yet.")
        return

    entries = data["entries"]
    summary = data.get("summary", {})

    # Summary metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Audits", summary.get("total_audits", 0))
    col2.metric("Flags Detected", summary.get("total_flags", 0))
    col3.metric("Current Risk", (summary.get("current_risk", "low")).capitalize())

    # Risk distribution chart
    risk_dist = summary.get("risk_distribution", {})
    if any(risk_dist.values()):
        st.markdown("**Risk Distribution**")
        risk_df = pd.DataFrame({
            "Risk Level": list(risk_dist.keys()),
            "Count": list(risk_dist.values()),
        })
        st.bar_chart(risk_df, x="Risk Level", y="Count")

    # Bias category breakdown
    cat_counts = summary.get("category_counts", {})
    if cat_counts:
        st.markdown("**Bias Categories Flagged**")
        cat_df = pd.DataFrame({
            "Category": list(cat_counts.keys()),
            "Count": list(cat_counts.values()),
        })
        cat_df = cat_df.sort_values("Count", ascending=False).head(10)
        st.bar_chart(cat_df, x="Category", y="Count")

    # Audit timeline table
    st.markdown("**Recent Audits**")
    timeline_rows = []
    for e in reversed(entries[-20:]):
        timeline_rows.append({
            "Time": e.get("timestamp", "")[:19].replace("T", " "),
            "Type": e.get("audit_type", "").replace("_", " ").title(),
            "Risk": e.get("overall_risk", "low").capitalize(),
            "Flags": e.get("flagged_count", 0),
        })
    st.dataframe(pd.DataFrame(timeline_rows), use_container_width=True, hide_index=True)


render_dashboard()
