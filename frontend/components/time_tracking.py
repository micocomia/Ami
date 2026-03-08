import streamlit as st
from utils.request_api import post_session_activity


def track_session_learning_start_time():
    user_id = st.session_state.get("userId")
    goal_id = st.session_state.get("selected_goal_id")
    session_index = st.session_state.get("selected_session_id")
    if user_id is None or goal_id is None or session_index is None:
        return
    post_session_activity(user_id, goal_id, session_index, "start")
