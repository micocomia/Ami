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
    "quiz_answers",
    "mastery_status",
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
    else:
        # Safety: if restored/persisted llm_type is no longer available, fall back.
        llm_type = st.session_state.get("llm_type")
        available_models = st.session_state.get("available_models", [])
        if (
            isinstance(llm_type, str)
            and isinstance(available_models, list)
            and available_models
            and llm_type not in available_models
        ):
            st.session_state["llm_type"] = available_models[0]
        elif not isinstance(llm_type, str) or not llm_type.strip():
            if isinstance(available_models, list) and available_models:
                st.session_state["llm_type"] = available_models[0]
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

    if "quiz_answers" not in st.session_state:
        st.session_state["quiz_answers"] = {}
    if "mastery_status" not in st.session_state:
        st.session_state["mastery_status"] = {}

    # Only load from the backend once per session.  Subsequent reruns keep
    # the in-memory session_state as the source of truth; periodic
    # save_persistent_state() calls flush it back to the backend.
    if "_state_loaded" not in st.session_state:
        try:
            load_persistent_state()
        except Exception:
            pass
        st.session_state["_state_loaded"] = True

def clear_user_state():
    """Clear all persisted user state from the current session.

    Called on logout and before switching users so that no data leaks
    between accounts. After this, initialize_session_state() will
    re-initialize keys to their defaults and load_persistent_state()
    will pull fresh data for the new user.
    """
    for k in PERSIST_KEYS:
        st.session_state.pop(k, None)
    # Clear ancillary keys not in PERSIST_KEYS
    for k in ["_state_loaded", "_last_save_ts", "auth_token", "_navigated_lp_once"]:
        st.session_state.pop(k, None)


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
    st.session_state["is_learning_path_ready"] = True if st.session_state["learning_path"] else False
    st.session_state["is_skill_gap_ready"] = True if st.session_state["skill_gaps"] else False
    # Always fetch goal's profile from backend (source of truth) and sync shared fields.
    # This ensures FSLSM/mastery changes made on other goals are reflected immediately,
    # and prevents stale or empty in-memory profiles from being shown.
    from utils.request_api import sync_profile
    user_id = st.session_state.get("userId")
    if user_id:
        merged = sync_profile(user_id, new_goal_id)
        if merged:
            goals[goal_id_idx]["learner_profile"] = merged
            st.session_state["learner_profile"] = merged
    # Update ready flag AFTER sync (reflects backend-fetched profile)
    st.session_state["is_learner_profile_ready"] = True if st.session_state["learner_profile"] else False
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

_PROFICIENCY_ORDER = ["unlearned", "beginner", "intermediate", "advanced", "expert"]


def _proficiency_idx(level: str) -> int:
    try:
        return _PROFICIENCY_ORDER.index(level)
    except ValueError:
        return 0


def propagate_profile_fields_to_other_goals(
    source_goal_id: int,
    sync_preferences: bool = False,
    sync_mastered_skills: bool = False,
):
    """Push learning_preferences and/or mastered_skills from one goal's profile to all others.

    Call this after updating a goal's profile so that changes are immediately reflected
    in all other goals without waiting for the next goal-switch sync.
    """
    from utils.request_api import save_learner_profile

    goals = st.session_state.get("goals", [])
    source_idx = index_goal_by_id(source_goal_id)
    if source_idx is None:
        return

    source_profile = goals[source_idx].get("learner_profile") or {}
    user_id = st.session_state.get("userId")

    for goal in goals:
        if goal["id"] == source_goal_id:
            continue
        target_profile = goal.get("learner_profile")
        if not target_profile:
            continue

        changed = False

        if sync_preferences:
            new_prefs = source_profile.get("learning_preferences")
            if new_prefs:
                target_profile["learning_preferences"] = new_prefs
                changed = True
            # learner_information is shared across all goals — always propagate it
            # so the text description stays in sync with FSLSM vectors and mastery
            new_learner_info = source_profile.get("learner_information", "")
            if new_learner_info:
                target_profile["learner_information"] = new_learner_info
                changed = True

        if sync_mastered_skills:
            # learner_information is shared — propagate it when cognitive status changes too
            new_learner_info = source_profile.get("learner_information", "")
            if new_learner_info and not sync_preferences:  # avoid double-write if both flags set
                target_profile["learner_information"] = new_learner_info
                changed = True
            source_mastered = source_profile.get("cognitive_status", {}).get("mastered_skills", [])
            if source_mastered:
                target_cs = target_profile.setdefault("cognitive_status", {})
                target_mastered = target_cs.get("mastered_skills", [])
                merged = {s["name"]: s for s in target_mastered if s.get("name")}
                for skill in source_mastered:
                    name = skill.get("name")
                    if not name:
                        continue
                    existing = merged.get(name)
                    if existing is None:
                        merged[name] = skill
                    else:
                        existing_idx = _proficiency_idx(existing.get("proficiency_level", "unlearned"))
                        new_idx = _proficiency_idx(skill.get("proficiency_level", "unlearned"))
                        if new_idx > existing_idx:
                            merged[name] = skill
                target_cs["mastered_skills"] = list(merged.values())
                # Remove newly mastered skills from in_progress_skills to keep state consistent
                mastered_names = set(merged.keys())
                in_progress = target_cs.get("in_progress_skills", [])
                target_cs["in_progress_skills"] = [
                    s for s in in_progress if s.get("name") not in mastered_names
                ]
                changed = True

        if changed:
            goal["learner_profile"] = target_profile
            if user_id:
                try:
                    save_learner_profile(user_id, goal["id"], target_profile)
                except Exception:
                    pass


def get_current_knowledge_point_uid():
    selected_gid = st.session_state["selected_goal_id"]
    selected_sid = st.session_state["selected_session_id"]
    selected_pid = st.session_state["selected_point_id"]
    return f"{selected_gid}-{selected_sid}-{selected_pid}"

def get_current_session_uid():
    selected_gid = st.session_state["selected_goal_id"]
    selected_sid = st.session_state["selected_session_id"]
    return f"{selected_gid}-{selected_sid}"
