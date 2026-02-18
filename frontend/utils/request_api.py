import json
import httpx
import streamlit as st
from config import backend_endpoint, use_mock_data, use_search
from datetime import datetime, timezone


def _debug_enabled() -> bool:
    """Front-end toggle (set by sidebar) to surface raw backend responses."""
    return bool(st.session_state.get("debug_api"))


def _coerce_jsonable(value):
    """
    Make payload fields JSON-friendly without accidentally stringifying dict/list.
    - If a string looks like JSON, try json.loads
    - If it's a Pydantic / dataclass-like object, try to dump to dict
    """
    if value is None:
        return None
    if isinstance(value, (dict, list, str, int, float, bool)):
        if isinstance(value, str):
            s = value.strip()
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                try:
                    return json.loads(s)
                except Exception:
                    return value
        return value
    # Pydantic v2
    for attr in ("model_dump", "dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return value



def _store_reasoning_fields(resp_json: dict) -> None:
    """Persist backend reasoning/trace into session_state if present."""
    if not isinstance(resp_json, dict):
        return
    reasoning = resp_json.get("reasoning")
    trace = resp_json.get("trace")
    # Prefer trace if available; otherwise fall back to reasoning
    if trace is not None:
        st.session_state["agent_reasoning"] = trace
    elif reasoning is not None:
        st.session_state["agent_reasoning"] = reasoning


def _normalize_learner_information(learner_information):
    """Backend expects a STRING for learner_information.

    - If we already have a string, pass through.
    - If we have a dict/list (from earlier UI steps), stringify as JSON.
    - If None, send empty string.
    """
    if learner_information is None:
        return ""
    if isinstance(learner_information, str):
        return learner_information
    try:
        return json.dumps(learner_information, ensure_ascii=False)
    except Exception:
        return str(learner_information)


def _normalize_skill_gaps(skill_gaps):
    """Backend expects a *string* for skill_gaps (FastAPI validation: string_type).

    We keep the UI-friendly Python list internally, but when sending to the backend we
    serialize to JSON text so the backend receives a valid string consistently.
    """
    if skill_gaps is None:
        return "[]"

    # Already a list/dict -> JSON string
    if isinstance(skill_gaps, (list, dict)):
        try:
            return json.dumps(skill_gaps, ensure_ascii=False)
        except Exception:
            return "[]"

    # Already a JSON-ish string -> keep as-is (best effort)
    if isinstance(skill_gaps, str):
        s = skill_gaps.strip()
        if not s:
            return "[]"
        # If it looks like JSON, keep it; otherwise wrap as a JSON string
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            return s
        try:
            return json.dumps(s, ensure_ascii=False)
        except Exception:
            return "[]"

    # Anything else -> stringify then JSON-encode
    try:
        return json.dumps(str(skill_gaps), ensure_ascii=False)
    except Exception:
        return "[]"



API_NAMES = {
    "auth_register": "auth/register",
    "auth_login": "auth/login",
    "chat_with_tutor": "chat-with-tutor",
    "refine_goal": "refine-learning-goal",
    "identify_skill_gap": "identify-skill-gap-with-info",
    "create_profile": "create-learner-profile-with-info",
    "update_profile": "update-learner-profile",
    "update_cognitive_status": "update-cognitive-status",
    "update_learning_preferences": "update-learning-preferences",
    "schedule_path": "schedule-learning-path",
    "schedule_path_agentic": "schedule-learning-path-agentic",
    "reschedule_path": "reschedule-learning-path",
    "adapt_path": "adapt-learning-path",
    "explore_knowledge_perspectives": "explore-knowledge-perspectives",
    "draft_knowledge_perspective": "draft-knowledge-perspective",
    "draft_point_perspectives": "draft-point-perspectives",
    "integrate_knowledge_document": "integrate-knowledge-document",
    "tailor_learning_content": "tailor-learning-content",
    "explore_knowledge_points": "explore-knowledge-points",
    "draft_knowledge_point": "draft-knowledge-point",
    "draft_knowledge_points": "draft-knowledge-points",
    "integrate_learning_document": "integrate-learning-document",
    "generate_document_quizzes": "generate-document-quizzes",
    "simulate_path_feedback": "simulate-path-feedback",
    "refine_path": "refine-learning-path",
    "iterative_refine_path": "iterative-refine-path",
    "audit_skill_gap_bias": "audit-skill-gap-bias",
    "validate_profile_fairness": "validate-profile-fairness",
}


def _set_api_debug_last(url: str, status: int | None, request_json, response_text: str | None) -> None:
    """Persist the last API call details so pages can render it (prevents 'flash then disappear')."""
    if not _debug_enabled():
        return
    st.session_state["api_debug_last"] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "status": status,
        "request_json": request_json,
        "response_text": response_text,
    }


def make_post_request(api_name, data, mock_data_path=None, timeout=500):
    """Send a POST request to the backend API, or return mock data if enabled.

    When API debug mode is enabled, we store the last request/response in
    st.session_state["api_debug_last"] so the UI can show it in a sidebar expander.
    """
    if use_mock_data and mock_data_path:
        return json.load(open(mock_data_path))

    backend_url = f"{backend_endpoint}{api_name}"

    try:
        response = httpx.post(backend_url, json=data, timeout=timeout)

        # Persist debug info for sidebar display (stable, no flashing)
        _set_api_debug_last(
            url=backend_url,
            status=response.status_code,
            request_json=data,
            response_text=response.text,
        )

        # Optional lightweight inline debug
        if _debug_enabled():
            st.caption(f"POST {backend_url}")
            st.write("HTTP status:", response.status_code)

        if response.status_code == 200:
            resp_json = response.json()
            _store_reasoning_fields(resp_json)
            return resp_json

        return None

    except Exception as e:
        _set_api_debug_last(
            url=backend_url,
            status=None,
            request_json=data,
            response_text=f"{type(e).__name__}: {e}",
        )
        return None


def extract_pdf_text(file):
    """Extract text from a PDF file using the backend API."""
    backend_url = f"{backend_endpoint}extract-pdf-text"
    try:
        files = {"file": (file.name, file.getvalue(), "application/pdf")}
        response = httpx.post(backend_url, files=files, timeout=60)
        if response.status_code == 200:
            return response.json().get("text", "")
        else:
            st.write("Failed to extract PDF text. Status code:", response.status_code)
            return ""
    except Exception as e:
        st.write("Failed to extract PDF text. Error:", e)
        return ""

def get_available_models(backend_endpoint):
    backend_url = f"{backend_endpoint}list-llm-models"
    try:
        response = httpx.get(backend_url, timeout=30)
        if response.status_code == 200:
            return response.json().get("models", [])
        else:
            # st.write("Failed to fetch available models. Status code:", response.status_code)
            return []
    except Exception as e:
        # st.write("Failed to fetch available models. Error:", e)
        return []

def chat_with_tutor(chat_messages, learner_profile, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "messages": str(chat_messages),
        "learner_profile": str(learner_profile),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request(API_NAMES["chat_with_tutor"], data, "./assets/data_example/ai)tutor_chat.json")
    return response.get("response") if response else None

def refine_learning_goal(learning_goal, learner_information, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request(API_NAMES["refine_goal"], data)
    return response.get("refined_goal") if response else "Refined learning goal"


def identify_skill_gap(
    learning_goal,
    learner_information,
    llm_type=None,
    method_name=None,
    user_id=None,
    goal_id=None,
):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["identify_skill_gap"], data, "./assets/data_example/skill_gap.json")
    if not response:
        return None, None, None
    return response.get("skill_gaps"), response.get("goal_assessment"), response.get("retrieved_sources")


def audit_skill_gap_bias(skill_gaps_dict, learner_information, llm_type=None, method_name=None):
    """Call the bias audit endpoint and return the audit result."""
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "skill_gaps": json.dumps(skill_gaps_dict),
        "learner_information": _normalize_learner_information(learner_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    return make_post_request(API_NAMES["audit_skill_gap_bias"], data)


def validate_profile_fairness(learner_profile, learner_information, persona_name="", llm_type=None):
    """Call the fairness validation endpoint and return the result."""
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    data = {
        "learner_profile": json.dumps(learner_profile) if isinstance(learner_profile, dict) else str(learner_profile),
        "learner_information": _normalize_learner_information(learner_information),
        "persona_name": persona_name,
        "llm_type": str(llm_type),
    }
    return make_post_request(API_NAMES["validate_profile_fairness"], data)


def create_learner_profile(
    learning_goal,
    learner_information,
    skill_gaps,
    llm_type=None,
    method_name=None,
    user_id=None,
    goal_id=None,
):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
        "skill_gaps": _normalize_skill_gaps(skill_gaps),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["create_profile"], data, "./assets/data_example/learner_profile.json")
    return response.get("learner_profile") if response else None

def update_learner_profile(learner_profile, learner_interactions, learner_information="", session_information="", llm_type=None, method_name=None, user_id=None, goal_id=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "learner_information": str(learner_information),
        "session_information": str(session_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_profile"], data, "./assets/data_example/learner_profile.json")
    return response.get("learner_profile") if response else None


def update_cognitive_status(learner_profile, session_information, llm_type=None, method_name=None, user_id=None, goal_id=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "session_information": str(session_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_cognitive_status"], data)
    return response.get("learner_profile") if response else None


def update_learning_preferences(learner_profile, learner_interactions, learner_information="", llm_type=None, method_name=None, user_id=None, goal_id=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "learner_information": str(learner_information),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_learning_preferences"], data)
    return response.get("learner_profile") if response else None


# @st.cache_resource
def schedule_learning_path(learner_profile, session_count=None, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    # Backend expects learner_profile as a string.
    # session_count must be an int.
    try:
        session_count_int = int(session_count) if session_count is not None else cfg["default_session_count"]
    except Exception:
        session_count_int = cfg["default_session_count"]

    data = {
        "learner_profile": str(learner_profile),
        "session_count": session_count_int,
    }

    response = make_post_request(API_NAMES["schedule_path"], data)
    if response:
        return {
            "learning_path": response.get("learning_path"),
            "retrieved_sources": response.get("retrieved_sources", []),
        }
    return None


def schedule_learning_path_agentic(learner_profile, session_count=None, llm_type=None, method_name=None):
    """Call the agentic learning path endpoint with auto-refinement."""
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    try:
        session_count_int = int(session_count) if session_count is not None else cfg["default_session_count"]
    except Exception:
        session_count_int = cfg["default_session_count"]

    data = {
        "learner_profile": str(learner_profile),
        "session_count": session_count_int,
    }

    response = make_post_request(API_NAMES["schedule_path_agentic"], data, timeout=120)
    if response:
        return {
            "learning_path": response.get("learning_path"),
            "agent_metadata": response.get("agent_metadata", {}),
        }
    return None


def adapt_learning_path(user_id, goal_id, new_learner_profile, llm_type=None, method_name=None):
    """Call the adaptive plan regeneration endpoint."""
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "new_learner_profile": str(new_learner_profile),
    }
    response = make_post_request(API_NAMES["adapt_path"], data, timeout=120)
    if response:
        return {
            "learning_path": response.get("learning_path"),
            "agent_metadata": response.get("agent_metadata", {}),
        }
    return None


def reschedule_learning_path(learning_path, learner_profile, session_count, other_feedback="", llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    # Backend expects learner_profile and learning_path as strings.
    try:
        session_count_int = int(session_count)
    except Exception:
        session_count_int = cfg["default_session_count"]
    data = {
        "learning_path": str(learning_path),
        "learner_profile": str(learner_profile),
        "session_count": session_count_int,
        "other_feedback": str(other_feedback),
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request(API_NAMES["reschedule_path"], data, "./assets/data_example/learning_path.json")
    return response.get("rescheduled_learning_path") if response else None

# @st.cache_resource
def generate_document_quizzes(learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learning_document": str(learning_document),
        "single_choice_count": single_choice_count,
        "multiple_choice_count": multiple_choice_count,
        "true_false_count": true_false_count,
        "short_answer_count": short_answer_count,
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request("generate-document-quizzes", data, "./assets/data_example/document_quiz.json")
    return response.get("document_quiz") if response else None

# @st.cache_resource
def explore_knowledge_points(learner_profile, learning_path, learning_session, llm_type=None, method_name=None):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
    }
    response = make_post_request("explore-knowledge-points", data, "./assets/data_example/knowledge_points.json")
    return response.get("knowledge_points") if response else None

# @st.cache_resource
def draft_knowledge_point(learner_profile, learning_path, learning_session, knowledge_points, knowledge_point, use_search, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "knowledge_point": str(knowledge_point),
        "use_search": use_search,
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request("draft-knowledge-point", data, "./assets/data_example/knowledge_point.json")
    return response.get("knowledge_draft") if response else None

# @st.cache_resource
def draft_knowledge_points(learner_profile, learning_path, learning_session, knowledge_points, allow_parallel, use_search, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "allow_parallel": allow_parallel,
        "use_search": use_search,
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request("draft-knowledge-points", data, "./assets/data_example/knowledge_points.json")
    return response.get("knowledge_drafts") if response else None

# @st.cache_resource
def integrate_learning_document(learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts, output_markdown=False, llm_type=None, method_name=None):
    cfg = get_app_config()
    llm_type = llm_type or cfg["default_llm_type"]
    method_name = method_name or cfg["default_method_name"]
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "knowledge_points": str(knowledge_points),
        "knowledge_drafts": str(knowledge_drafts),
        "output_markdown": output_markdown,
        "llm_type": str(llm_type),
        "method_name": str(method_name),
    }
    response = make_post_request("integrate-learning-document", data, "./assets/data_example/learning_document.json")
    if output_markdown:
        return response.get("learning_document") if response else None
    else:
        return response.get("learning_document") if response else None

def evaluate_mastery(user_id, goal_id, session_index, quiz_answers):
    """Submit quiz answers for mastery evaluation."""
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "session_index": int(session_index),
        "quiz_answers": quiz_answers,
    }
    response = make_post_request("evaluate-mastery", data)
    return response if response else None


def get_session_mastery_status(user_id, goal_id):
    """Get mastery status for all sessions in a goal."""
    url = f"{backend_endpoint}session-mastery-status/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_behavioral_metrics(user_id, goal_id=None):
    """Fetch computed behavioral metrics from the backend."""
    url = f"{backend_endpoint}behavioral-metrics/{user_id}"
    if goal_id is not None:
        url += f"?goal_id={goal_id}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_user_state(backend_ep, user_id):
    """GET /user-state/{user_id} → (status_code, response_json)"""
    if use_mock_data:
        return 404, {"detail": "mock mode — no persisted state"}
    url = f"{backend_ep}user-state/{user_id}"
    try:
        resp = httpx.get(url, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def save_user_state(backend_ep, user_id, state):
    """PUT /user-state/{user_id} → (status_code, response_json)"""
    if use_mock_data:
        return 200, {"ok": True}
    url = f"{backend_ep}user-state/{user_id}"
    try:
        resp = httpx.put(url, json={"state": state}, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def delete_user_state(backend_ep, user_id):
    """DELETE /user-state/{user_id} → (status_code, response_json)"""
    if use_mock_data:
        return 200, {"ok": True}
    url = f"{backend_ep}user-state/{user_id}"
    try:
        resp = httpx.delete(url, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def auth_register(username, password):
    """Register a new user via the backend."""
    if use_mock_data:
        return 200, {"token": "mock-token", "username": username}
    data = {"username": username, "password": password}
    backend_url = f"{backend_endpoint}{API_NAMES['auth_register']}"
    try:
        response = httpx.post(backend_url, json=data, timeout=30)
        return response.status_code, response.json()
    except Exception as e:
        return None, {"detail": str(e)}


def auth_login(username, password):
    """Authenticate a user via the backend."""
    if use_mock_data:
        return 200, {"token": "mock-token", "username": username}
    data = {"username": username, "password": password}
    backend_url = f"{backend_endpoint}{API_NAMES['auth_login']}"
    try:
        response = httpx.post(backend_url, json=data, timeout=30)
        return response.status_code, response.json()
    except Exception as e:
        return None, {"detail": str(e)}


def auth_delete_user(token):
    """Delete the authenticated user's account via DELETE /auth/user."""
    if use_mock_data:
        return 200, {"ok": True}
    url = f"{backend_endpoint}auth/user"
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = httpx.delete(url, headers=headers, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def sync_profile(user_id, goal_id):
    """Sync a goal's profile with shared fields from all other goals."""
    backend_url = f"{backend_endpoint}sync-profile/{user_id}/{goal_id}"
    try:
        response = httpx.post(backend_url, timeout=30)
        if response.status_code == 200:
            return response.json().get("learner_profile")
    except Exception:
        pass
    return None


def get_learner_profile(user_id, goal_id):
    """Retrieve an existing learner profile from the backend store. Returns None if not found."""
    url = f"{backend_endpoint}profile/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("learner_profile")
    except Exception:
        pass
    return None


def save_learner_profile(user_id, goal_id, learner_profile):
    """Persist a learner profile to the backend store without triggering an LLM call."""
    backend_url = f"{backend_endpoint}profile/{user_id}/{goal_id}"
    try:
        response = httpx.put(backend_url, json={"learner_profile": learner_profile}, timeout=30)
        return response.status_code == 200
    except Exception:
        return False


def get_personas():
    """GET /personas → dict of personas. Falls back to local data on failure."""
    from utils.personas import PERSONAS as LOCAL_PERSONAS
    if use_mock_data:
        return LOCAL_PERSONAS
    url = f"{backend_endpoint}personas"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("personas", LOCAL_PERSONAS)
        return LOCAL_PERSONAS
    except Exception:
        return LOCAL_PERSONAS


# ---- Application config (fetched from backend, with local fallback) ----

_LOCAL_APP_CONFIG = {
    "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
    "default_session_count": 8,
    "default_llm_type": "gpt4o",
    "default_method_name": "genmentor",
    "motivational_trigger_interval_secs": 180,
    "max_refinement_iterations": 5,
    "fslsm_thresholds": {
        "perception": {
            "low_threshold": -0.3,
            "high_threshold": 0.3,
            "low_label": "Concrete examples and practical applications",
            "high_label": "Conceptual and theoretical explanations",
            "neutral_label": "A mix of practical and conceptual content",
        },
        "understanding": {
            "low_threshold": -0.3,
            "high_threshold": 0.3,
            "low_label": "presented in step-by-step sequences",
            "high_label": "with big-picture overviews first",
            "neutral_label": "balancing sequential detail and big-picture context",
        },
        "processing": {
            "low_threshold": -0.3,
            "high_threshold": 0.3,
            "low_label": "Hands-on and interactive activities",
            "high_label": "Reading and observation-based learning",
            "neutral_label": "A balance of interactive and reflective activities",
        },
        "input": {
            "low_threshold": -0.3,
            "high_threshold": 0.3,
            "low_label": "with diagrams, charts, and videos",
            "high_label": "with text-based materials and lectures",
            "neutral_label": "using both visual and verbal materials",
        },
    },
}

_cached_app_config = None


def get_app_config():
    """GET /config → app configuration dict. Falls back to local defaults."""
    global _cached_app_config
    if _cached_app_config is not None:
        return _cached_app_config
    if use_mock_data:
        _cached_app_config = _LOCAL_APP_CONFIG
        return _cached_app_config
    url = f"{backend_endpoint}config"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            _cached_app_config = resp.json()
            return _cached_app_config
    except Exception:
        pass
    _cached_app_config = _LOCAL_APP_CONFIG
    return _cached_app_config
