import streamlit as st
import time
from utils.state import initialize_session_state, change_selected_goal_id, save_persistent_state, load_persistent_state
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

# ---- Learning analytics (defensive) ----
# The app may reach this page before goals are loaded/created. Avoid crashes.
st.session_state.setdefault("learned_skills_history", {})

goals = st.session_state.get("goals") or []
selected = st.session_state.get("selected_goal_id", 0)

goal = None
# If selected is a list index
if isinstance(selected, int) and 0 <= selected < len(goals):
    goal = goals[selected]
# If selected is an id and goals are dicts with "id"
elif goals:
    for g in goals:
        try:
            if isinstance(g, dict) and g.get("id") == selected:
                goal = g
                break
        except Exception:
            pass
    # Fallback: pick first goal to keep app functional
    if goal is None:
        goal = goals[0]
        st.session_state["selected_goal_id"] = 0

if goal is not None:
    goal["start_time"] = time.time()
    try:
        save_persistent_state()
    except Exception:
        pass

    # Compute mastery rate defensively
    mastery_rate = 0
    try:
        unlearned_skill = len(goal["learner_profile"]["cognitive_status"]["in_progress_skills"])
        learned_skill = len(goal["learner_profile"]["cognitive_status"]["mastered_skills"])
        all_skill = learned_skill + unlearned_skill
        mastery_rate = (learned_skill / all_skill) if all_skill else 0
    except Exception:
        # If profile keys are missing, skip analytics quietly
        all_skill = 0

    # Track mastery history per-goal id if available
    goal_id = None
    try:
        goal_id = goal.get("id") if isinstance(goal, dict) else None
    except Exception:
        goal_id = None

    if goal_id is not None:
        if goal_id not in st.session_state["learned_skills_history"]:
            st.session_state["learned_skills_history"][goal_id] = []
            try:
                save_persistent_state()
            except Exception:
                pass

        # First sample
        if all_skill:
            if st.session_state["learned_skills_history"][goal_id] == []:
                st.session_state["learned_skills_history"][goal_id].append(mastery_rate)
                try:
                    save_persistent_state()
                except Exception:
                    pass

        # Periodic sample every 10 minutes
        try:
            if (time.time() - goal["start_time"]) > 600:
                goal["start_time"] = time.time()
                try:
                    save_persistent_state()
                except Exception:
                    pass
                st.session_state["learned_skills_history"][goal_id].append(mastery_rate)
                try:
                    save_persistent_state()
                except Exception:
                    pass
        except Exception:
            pass

        # Keep last 10 points
        if len(st.session_state["learned_skills_history"][goal_id]) > 10:
            st.session_state["learned_skills_history"][goal_id].pop(0)
            try:
                save_persistent_state()
            except Exception:
                pass

    try:
        save_persistent_state()
    except Exception:
        pass
# ---- End learning analytics ----

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

