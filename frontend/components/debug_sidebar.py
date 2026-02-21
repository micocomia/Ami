import streamlit as st

from config import backend_endpoint


def render_debug_sidebar():
    """Render API debug expanders in the sidebar. Available on all pages."""
    st.session_state.setdefault("debug_api", False)

    with st.sidebar:
        with st.expander("Debug (API)", expanded=False):
            st.session_state["debug_api"] = st.checkbox(
                "Enable API debug mode",
                value=st.session_state["debug_api"],
                help="Shows endpoint/payload preview and enables deeper error visibility.",
            )
            st.write("Backend endpoint:", backend_endpoint)
            st.write("UserId:", st.session_state.get("userId"))

            goal = st.session_state.get("to_add_goal")
            if goal:
                st.write("Learning goal:", goal.get("learning_goal"))

        with st.sidebar.expander("Debug (API) — Last request/response", expanded=True):
            last = st.session_state.get("api_debug_last")
            if not last:
                st.info("No API calls captured yet.")
            else:
                st.write("Time:", last.get("ts"))
                st.write("URL:", last.get("url"))
                st.write("Status:", last.get("status"))
                st.caption("Request JSON")
                st.json(last.get("request_json"))
                st.caption("Response")
                st.code(last.get("response_text", ""))
