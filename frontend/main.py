import streamlit as st
from utils.state import (
    change_selected_goal_id,
    initialize_session_state,
    normalize_selected_goal_id,
    save_persistent_state,
)
from components.topbar import logout
initialize_session_state()


# --- Reasoning UI helpers (safe, optional) ---
def _extract_reasoning_payload():
    """Find reasoning/trace data in session_state, regardless of how pages store it."""
    # Direct keys
    direct_keys = [
        "agent_reasoning",
        "reasoning",
        "trace",
        "agent_trace",
        "latest_response",
        "last_response",
        "last_agent_response",
    ]
    for k in direct_keys:
        v = st.session_state.get(k, None)
        if v:
            # If it's a full API response dict, try to pick a reasoning-like field inside it.
            if isinstance(v, dict):
                for kk in ("reasoning", "rationale", "explanation", "trace", "agent_reasoning", "agent_trace"):
                    if v.get(kk):
                        return f"{k}.{kk}", v.get(kk)
            return k, v

    # Nested candidates inside a response dict stored under common keys
    for response_key in ("latest_response", "last_response", "last_agent_response"):
        resp = st.session_state.get(response_key)
        if isinstance(resp, dict):
            for kk in ("reasoning", "rationale", "explanation", "trace", "agent_reasoning", "agent_trace"):
                if resp.get(kk):
                    return f"{response_key}.{kk}", resp.get(kk)

    return None, None


def render_reasoning_panel(container):
    """Render a toggle + expander that shows agent reasoning when available."""
    st.session_state.setdefault("show_agent_reasoning", False)
    container.checkbox("Show agent reasoning", key="show_agent_reasoning")

    if st.session_state.get("show_agent_reasoning"):
        source, payload = _extract_reasoning_payload()
        with container.expander("Agent reasoning", expanded=True):
            if payload is None:
                container.info(
                    "No reasoning available yet. "
                    "This will appear once the backend returns a 'reasoning' or 'trace' field "
                    "and the page stores it in session_state."
                )
            else:
                container.caption(f"Source: {source}")
                if isinstance(payload, (dict, list)):
                    container.json(payload)
                else:
                    container.write(payload)
# --- End reasoning UI helpers ---


st.session_state.setdefault("_autosave_enabled", True)
try:
    save_persistent_state()
except Exception:
    pass

from components.chatbot import render_chatbot

st.set_page_config(page_title="Ami", page_icon="🧠", layout="wide")
st.logo("./assets/avatar.png")
st.markdown('<style>' + open('./assets/css/main.css').read() + '</style>', unsafe_allow_html=True)

if not st.session_state.get("logged_in", False):
    from components.topbar import login
    st.title("Welcome to Ami")
    st.write("Please log in or register to continue.")
    if st.button("Login / Register", icon=":material/account_circle:"):
        login()
    st.stop()

try:
    if st.session_state.get("if_complete_onboarding", False) and not st.session_state.get("_navigated_lp_once", False):
        st.session_state["_navigated_lp_once"] = True
        try:
            st.switch_page("pages/learning_path.py")
        except Exception:
            pass
except Exception:
    pass


if st.session_state["show_chatbot"]:
    render_chatbot()

if st.session_state["if_complete_onboarding"]:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=False, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=True, url_path="learning_path")
else:
    onboarding = st.Page("pages/onboarding.py", title="Onboarding", icon=":material/how_to_reg:", default=True, url_path="onboarding")
    learning_path = st.Page("pages/learning_path.py", title="Learning Path", icon=":material/route:", default=False, url_path="learning_path")
skill_gaps = st.Page("pages/skill_gap.py", title="Skill Gap", icon=":material/insights:", default=False, url_path="skill_gap")
knowledge_document = st.Page("pages/knowledge_document.py", title="Resume Learning", icon=":material/menu_book:", default=False, url_path="knowledge_document")
learner_profile = st.Page("pages/learner_profile.py", title="My Profile", icon=":material/person:", default=False, url_path="learner_profile")
goal_management = st.Page("pages/goal_management.py", title="Goal Management", icon=":material/flag:", default=False, url_path="goal_management")
dashboard = st.Page("pages/dashboard.py", title="Analytics Dashboard", icon=":material/browse:", default=False, url_path="dashboard")

# Learning Analytics Dashboard
if not st.session_state["if_complete_onboarding"]:
    nav_position = "sidebar"
    pg = st.navigation({"Ami": [onboarding, skill_gaps, learning_path]}, position="hidden", expanded=True)
else:
    nav_position = "sidebar"
    pg = st.navigation({"Ami": [goal_management, learning_path, knowledge_document, learner_profile, dashboard]}, position=nav_position, expanded=True)
    with st.sidebar:
        st.caption(f"Signed in as **{st.session_state.get('userId', '')}**")
        if st.button("Logout", icon=":material/exit_to_app:"):
            logout()
            st.rerun()

st.divider()
# Optional: display agent reasoning/trace for ethics/transparency demos
render_reasoning_panel(st.sidebar)

# API debug sidebar (available on all pages)
from components.debug_sidebar import render_debug_sidebar
render_debug_sidebar()

goals = st.session_state.get("goals") or []
if goals:
    if normalize_selected_goal_id():
        try:
            save_persistent_state()
        except Exception:
            pass

try:
    if st.session_state.get("_autosave_enabled", True):
        save_persistent_state()
except Exception:
    pass

if len(st.session_state["goals"]) != 0:
    change_selected_goal_id(st.session_state["selected_goal_id"])
    try:
        save_persistent_state()
    except Exception:
        pass

pg.run()
