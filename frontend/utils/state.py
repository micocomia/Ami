import streamlit as st
import config

def load_persistent_state():
    """Load backend-backed goals into local session state."""
    from utils.request_api import list_goals

    user_id = st.session_state.get("userId")
    if not user_id or user_id == "default":
        return False
    goals = list_goals(user_id)
    st.session_state["goals"] = goals or []
    st.session_state["if_complete_onboarding"] = bool(st.session_state["goals"])
    if st.session_state["goals"] and st.session_state.get("selected_goal_id") is None:
        st.session_state["selected_goal_id"] = st.session_state["goals"][0]["id"]
    return True


def save_persistent_state():
    """Compatibility no-op; domain state is now persisted via explicit endpoints."""
    return True


def delete_persistent_state():
    """Compatibility no-op after /user-state removal."""
    return True


def initialize_session_state():
    for key in ["if_complete_onboarding", "is_learner_profile_ready", "is_learning_path_ready", "is_skill_gap_ready", "is_knowledge_document_ready"]:
        if key not in st.session_state:
            st.session_state[key] = False

    if "backend_endpoint" not in st.session_state:
        st.session_state["backend_endpoint"] = config.backend_endpoint
    if "backend_public_endpoint" not in st.session_state:
        st.session_state["backend_public_endpoint"] = config.backend_public_endpoint

    if "available_models" not in st.session_state:
        from utils.request_api import check_backend, get_app_config
        cfg = check_backend(st.session_state["backend_endpoint"]) or get_app_config()
        st.session_state["available_models"] = [cfg["default_llm_type"]] if cfg else ["openai/gpt-4o"]

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

    for key in ["learner_information", "learner_information_pdf", "learner_information_text", "learner_persona"]:
        if key not in st.session_state:
            st.session_state[key] = ""

    if "if_refining_learning_goal" not in st.session_state:
        st.session_state["if_refining_learning_goal"] = False

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

    if "quiz_answers" not in st.session_state:
        st.session_state["quiz_answers"] = {}
    if "mastery_status" not in st.session_state:
        st.session_state["mastery_status"] = {}

    if "_state_loaded" not in st.session_state:
        try:
            load_persistent_state()
        except Exception:
            pass
        st.session_state["_state_loaded"] = True

    selected_changed = normalize_selected_goal_id()
    if selected_changed:
        try:
            save_persistent_state()
        except Exception:
            pass

def clear_user_state():
    """Clear all persisted user state from the current session.

    Called on logout and before switching users so that no data leaks
    between accounts. After this, initialize_session_state() will
    re-initialize keys to their defaults and load_persistent_state()
    will pull fresh data for the new user.
    """
    for k in [
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
        "if_updating_learner_profile",
        "selected_goal_id",
        "selected_session_id",
        "selected_point_id",
        "to_add_goal",
        "userId",
        "document_caches",
        "path_feedback_cache",
        "if_simulating_feedback",
        "if_refining_path",
        "quiz_answers",
        "mastery_status",
    ]:
        st.session_state.pop(k, None)
    # Clear ancillary keys not in PERSIST_KEYS
    for k in ["_state_loaded", "_last_save_ts", "auth_token", "_navigated_lp_once"]:
        st.session_state.pop(k, None)
    # Clear dynamic per-goal keys that aren't in the static list above
    for k in list(st.session_state.keys()):
        if k.startswith("learning_path_schedule_attempted_") or k.startswith("auto_adapt_inflight_") or k.startswith("goal_runtime_state_"):
            st.session_state.pop(k, None)


def get_new_goal_uid():
    return max(goal["id"] for goal in st.session_state.goals) + 1 if st.session_state.goals else 0

def reset_to_add_goal():
    st.session_state["to_add_goal"] = {
        "learning_goal": "",
        "skill_gaps": [],
        "goal_assessment": None,
        "goal_context": {},
        "retrieved_sources": [],
        "learner_profile": {},
        "learning_path": [],
        "is_completed": False,
        "is_deleted": False
    }
    return st.session_state["to_add_goal"]


def index_goal_by_id(goal_id):
    goals = st.session_state.get("goals", [])
    if not isinstance(goals, list):
        return None
    for idx, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        gid = goal.get("id")
        if gid == goal_id or str(gid) == str(goal_id):
            return idx
    return None


def get_goal_by_id(goal_id):
    idx = index_goal_by_id(goal_id)
    if idx is None:
        return None
    goals = st.session_state.get("goals", [])
    if not isinstance(goals, list) or idx >= len(goals):
        return None
    goal = goals[idx]
    return goal if isinstance(goal, dict) else None


def get_selected_goal():
    return get_goal_by_id(st.session_state.get("selected_goal_id"))


def normalize_selected_goal_id():
    goals = st.session_state.get("goals", [])
    if not isinstance(goals, list) or not goals:
        return False

    selected = st.session_state.get("selected_goal_id")
    if get_goal_by_id(selected) is not None:
        return False

    normalized = None
    if isinstance(selected, int) and 0 <= selected < len(goals):
        maybe = goals[selected]
        if isinstance(maybe, dict):
            normalized = maybe.get("id")
    else:
        try:
            selected_int = int(selected)
            if 0 <= selected_int < len(goals):
                maybe = goals[selected_int]
                if isinstance(maybe, dict):
                    normalized = maybe.get("id")
        except Exception:
            pass

    if normalized is None:
        for goal in goals:
            if isinstance(goal, dict) and not goal.get("is_deleted"):
                normalized = goal.get("id")
                break
    if normalized is None:
        for goal in goals:
            if isinstance(goal, dict):
                normalized = goal.get("id")
                break
    if normalized is None:
        return False

    if st.session_state.get("selected_goal_id") != normalized:
        st.session_state["selected_goal_id"] = normalized
        return True
    return False

def change_selected_goal_id(new_goal_id):
    goals = st.session_state.get("goals", [])
    if not isinstance(goals, list):
        return
    goal_id_idx = index_goal_by_id(new_goal_id)
    if goal_id_idx is None:
        normalize_selected_goal_id()
        return

    if new_goal_id == st.session_state["selected_goal_id"]:
        return

    st.session_state["selected_goal_id"] = new_goal_id
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

def get_existing_goal_id_list():
    return [goal["id"] for goal in st.session_state["goals"]]

def add_new_goal(learning_goal="", skill_gaps=[], goal_assessment=None, learner_profile={}, learning_path=[], is_completed=False, is_deleted=False, **_kwargs):
    try:
        from utils.request_api import create_goal, sync_profile
    except ModuleNotFoundError:
        create_goal = None
        sync_profile = None
    passthrough_keys = (
        "goal_context",
        "retrieved_sources",
        "bias_audit",
        "profile_fairness",
        "_last_identified_goal",
    )
    goal_info = {
        "learning_goal": learning_goal,
        "skill_gaps": skill_gaps,
        "goal_assessment": goal_assessment,
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "is_completed": is_completed,
        "is_deleted": is_deleted
    }
    for key in passthrough_keys:
        if key in _kwargs:
            goal_info[key] = _kwargs[key]
    user_id = st.session_state.get("userId")
    created = create_goal(user_id, goal_info) if callable(create_goal) and user_id else None
    if created and user_id and callable(sync_profile):
        merged = sync_profile(user_id, created["id"])
        if merged:
            created["learner_profile"] = merged
    if not created:
        goal_uid = get_new_goal_uid()
        created = {"id": goal_uid, **goal_info}
    st.session_state.goals.append(created)
    reset_to_add_goal()
    return created["id"]

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
    """Push profile fields from source_goal to all other goals via the backend.

    When sync_preferences is True, the backend copies the source goal's
    learning_preferences (including FSLSM dimensions) and behavioral_patterns
    to every other goal the user has, keeping them in sync after an FSLSM edit.
    """
    if sync_preferences:
        user_id = st.session_state.get("userId")
        if user_id and source_goal_id is not None:
            from utils.request_api import propagate_learner_profile_to_other_goals
            propagate_learner_profile_to_other_goals(user_id, source_goal_id)
    try:
        load_persistent_state()
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
