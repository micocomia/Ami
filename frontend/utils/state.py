import time
import streamlit as st
from collections import defaultdict
import config

PERSIST_KEYS = [
    "if_complete_onboarding",
    "sample_number",
    "logged_in",
    "show_chatbot",
    "llm_type",
    "tutor_messages",
    "goals",
    "learner_information",
    "learner_information_pdf",
    "learner_information_text",
    "learner_persona",
    "if_refining_learning_goal",
    "if_rescheduling_learning_path",
    "if_updating_learner_profile",
    "selected_goal_id",
    "selected_session_id",
    "selected_point_id",
    "to_add_goal",
    "learned_skills_history",
    "userId",
    "document_caches",
    "session_learning_times",
    "path_feedback_cache",
    "if_simulating_feedback",
    "if_refining_path",
]

# Minimum interval between HTTP saves (seconds)
_SAVE_DEBOUNCE_SECS = 1.0


def load_persistent_state():
    """Load persisted keys from the backend into st.session_state."""
    from utils.request_api import get_user_state as _api_get

    user_id = st.session_state.get("userId", "default")
    backend_ep = st.session_state.get("backend_endpoint", config.backend_endpoint)
    status, data = _api_get(backend_ep, user_id)
    if status != 200:
        return False
    state = data.get("state", {})
    for k, v in state.items():
        if k in PERSIST_KEYS:
            st.session_state[k] = v
    return True


def save_persistent_state():
    """Save whitelisted st.session_state keys to the backend.

    Debounced: at most one HTTP PUT per ``_SAVE_DEBOUNCE_SECS`` seconds.
    The caller never needs to know whether the write was debounced away —
    the final save at the end of each Streamlit rerun will always go through
    because enough time will have elapsed (or because a new rerun starts).
    """
    from utils.request_api import save_user_state as _api_put

    now = time.time()
    last = st.session_state.get("_last_save_ts", 0.0)
    if now - last < _SAVE_DEBOUNCE_SECS:
        return True  # debounced — skip

    user_id = st.session_state.get("userId", "default")
    backend_ep = st.session_state.get("backend_endpoint", config.backend_endpoint)
    payload = {}
    for k in PERSIST_KEYS:
        if k in st.session_state:
            try:
                payload[k] = st.session_state[k]
            except Exception:
                pass
    status, _resp = _api_put(backend_ep, user_id, payload)
    if status == 200:
        st.session_state["_last_save_ts"] = now
        return True
    return False


def delete_persistent_state():
    """Delete the user's persisted state on the backend."""
    from utils.request_api import delete_user_state as _api_del

    user_id = st.session_state.get("userId", "default")
    backend_ep = st.session_state.get("backend_endpoint", config.backend_endpoint)
    status, _resp = _api_del(backend_ep, user_id)
    return status == 200


def initialize_session_state():
    for key in ["if_complete_onboarding", "is_learner_profile_ready", "is_learning_path_ready", "is_skill_gap_ready", "is_knowledge_document_ready"]:
        if key not in st.session_state:
            st.session_state[key] = False

    if "backend_endpoint" not in st.session_state:
        st.session_state["backend_endpoint"] = config.backend_endpoint

    if "available_models" not in st.session_state:
        from utils.request_api import get_available_models, get_app_config
        models = get_available_models(config.backend_endpoint)
        if models:
            st.session_state["available_models"] = [f"{m.get('model_provider', '')}/{m.get('model_name', '')}" for m in models]
        else:
            cfg = get_app_config()
            st.session_state["available_models"] = [cfg["default_llm_type"]]

    if "llm_type" not in st.session_state:
        if len(st.session_state["available_models"]) > 0:
            st.session_state["llm_type"] = st.session_state["available_models"][0]
        else:
            st.session_state["llm_type"] = "None"

    if "userId" not in st.session_state:
        st.session_state["userId"] = "TestUser"
        
    if "sample_number" not in st.session_state:
        st.session_state["sample_number"] = 2
        
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "show_chatbot" not in st.session_state:
        st.session_state["show_chatbot"] = True

    if "tutor_messages" not in st.session_state:
        st.session_state["tutor_messages"] = []

    if "selected_page" not in st.session_state:
        st.session_state["selected_page"] = "Onboarding"

    if "goals" not in st.session_state:
        st.session_state["goals"] = []
    
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = {}
        
    if "document_caches" not in st.session_state:
        st.session_state["document_caches"] = {}

    if "session_learning_times" not in st.session_state:
        st.session_state["session_learning_times"] = {}

    for key in ["learner_information", "learner_information_pdf", "learner_information_text", "learner_persona"]:
        if key not in st.session_state:
            st.session_state[key] = ""

    if "if_refining_learning_goal" not in st.session_state:
        st.session_state["if_refining_learning_goal"] = False

    if "if_rescheduling_learning_path" not in st.session_state:
        st.session_state["if_rescheduling_learning_path"] = False

    if "if_updating_learner_profile" not in st.session_state:
        st.session_state["if_updating_learner_profile"] = False

    if "path_feedback_cache" not in st.session_state:
        st.session_state["path_feedback_cache"] = {}
    if "if_simulating_feedback" not in st.session_state:
        st.session_state["if_simulating_feedback"] = False
    if "if_refining_path" not in st.session_state:
        st.session_state["if_refining_path"] = False

    for key in ["selected_goal_id", "selected_session_id", "selected_point_id"]:
        if key not in st.session_state:
            st.session_state[key] = 0

    if "to_add_goal" not in st.session_state:
        reset_to_add_goal()

    if 'learned_skills_history' not in st.session_state:
        st.session_state['learned_skills_history'] = {}

    # Only load from the backend once per session.  Subsequent reruns keep
    # the in-memory session_state as the source of truth; periodic
    # save_persistent_state() calls flush it back to the backend.
    if "_state_loaded" not in st.session_state:
        try:
            load_persistent_state()
        except Exception:
            pass
        st.session_state["_state_loaded"] = True

def get_new_goal_uid():
    return max(goal["id"] for goal in st.session_state.goals) + 1 if st.session_state.goals else 0

def reset_to_add_goal():
    st.session_state["to_add_goal"] = {
        "learning_goal": "",
        "skill_gaps": [],
        "goal_assessment": None,
        "learner_profile": {},
        "learning_path": [],
        "is_completed": False,
        "is_deleted": False
    }
    return st.session_state["to_add_goal"]


def index_goal_by_id(goal_id):
    goal_id_list = [goal["id"] for goal in st.session_state["goals"]]
    try:
        return goal_id_list.index(goal_id)
    except ValueError:
        return None

def change_selected_goal_id(new_goal_id):
    if new_goal_id == st.session_state["selected_goal_id"]:
        return
    goals = st.session_state["goals"]
    st.session_state["selected_goal_id"] = new_goal_id
    goal_id_list = [goal["id"] for goal in goals]
    goal_id_idx = goal_id_list.index(new_goal_id)
    st.session_state["learning_goal"] = goals[goal_id_idx]["learning_goal"]
    st.session_state["learner_profile"] = goals[goal_id_idx]["learner_profile"]
    st.session_state["skill_gaps"] = goals[goal_id_idx]["skill_gaps"]
    st.session_state["learning_path"] = goals[goal_id_idx]["learning_path"]
    st.session_state["selected_session_id"] = 0
    st.session_state["selected_point_id"] = 0
    # status
    st.session_state["is_learner_profile_ready"] = True if st.session_state["learner_profile"] else False
    st.session_state["is_learning_path_ready"] = True if st.session_state["learning_path"] else False
    st.session_state["is_skill_gap_ready"] = True if st.session_state["skill_gaps"] else False
    # persist change
    try:
        save_persistent_state()
    except Exception:
        pass

def get_existing_goal_id_list():
    return [goal["id"] for goal in st.session_state["goals"]]

def add_new_goal(learning_goal="", skill_gaps=[], goal_assessment=None, learner_profile={}, learning_path=[], is_completed=False, is_deleted=False, **_kwargs):
    goal_uid = get_new_goal_uid()
    goal_info = {
        "id": goal_uid,
        "learning_goal": learning_goal,
        "skill_gaps": skill_gaps,
        "goal_assessment": goal_assessment,
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "is_completed": is_completed,
        "is_deleted": is_deleted
    }
    st.session_state.goals.append(goal_info)
    goal_idx = index_goal_by_id(goal_uid)
    reset_to_add_goal()
    # persist after adding a goal
    try:
        save_persistent_state()
    except Exception:
        pass
    return goal_idx

def get_current_knowledge_point_uid():
    selected_gid = st.session_state["selected_goal_id"]
    selected_sid = st.session_state["selected_session_id"]
    selected_pid = st.session_state["selected_point_id"]
    return f"{selected_gid}-{selected_sid}-{selected_pid}"

def get_current_session_uid():
    selected_gid = st.session_state["selected_goal_id"]
    selected_sid = st.session_state["selected_session_id"]
    return f"{selected_gid}-{selected_sid}"
