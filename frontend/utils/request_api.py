import json
import os
import httpx
import streamlit as st
from typing import Optional
from config import backend_endpoint, use_mock_data, use_search
from datetime import datetime, timezone


def _get_backend_endpoint() -> str:
    """Resolve backend endpoint from live session state, falling back to config."""
    endpoint = st.session_state.get("backend_endpoint", backend_endpoint)
    if not isinstance(endpoint, str) or not endpoint.strip():
        endpoint = backend_endpoint
    endpoint = endpoint.strip()
    if not endpoint.endswith("/"):
        endpoint += "/"
    return f"{endpoint}v1/"


def _auth_headers() -> dict:
    """Return Authorization header dict if an auth token is present."""
    token = st.session_state.get("auth_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _normalize_endpoint(endpoint: Optional[str]) -> str:
    value = (endpoint or "").strip()
    if not value:
        return _get_backend_endpoint()
    return value if value.endswith("/") else f"{value}/"


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
    "goals": "goals",
    "goal_runtime_state": "goal-runtime-state",
    "learning_content_cache": "learning-content",
    "session_activity": "session-activity",
    "complete_session": "complete-session",
    "submit_content_feedback": "submit-content-feedback",
    "dashboard_metrics": "dashboard-metrics",
    "chat_with_tutor": "chat-with-tutor",
    "refine_goal": "refine-learning-goal",
    "identify_skill_gap": "identify-skill-gap-with-info",
    "create_profile": "create-learner-profile-with-info",
    "update_profile": "update-learner-profile",
    "update_cognitive_status": "update-cognitive-status",
    "update_learning_preferences": "update-learning-preferences",
    "update_learner_information": "update-learner-information",
    "schedule_path": "schedule-learning-path",
    "schedule_path_agentic": "schedule-learning-path-agentic",
    "adapt_path": "adapt-learning-path",
    "generate_learning_content": "generate-learning-content",
    "simulate_path_feedback": "simulate-path-feedback",
    "refine_path": "refine-learning-path",
    "iterative_refine_path": "iterative-refine-path",
    "audit_skill_gap_bias": "audit-skill-gap-bias",
    "validate_profile_fairness": "validate-profile-fairness",
    "audit_content_bias": "audit-content-bias",
    "audit_chatbot_bias": "audit-chatbot-bias",
    "reset_mastery_attempt": "reset-mastery-attempt",
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

    backend_url = f"{_get_backend_endpoint()}{api_name}"

    try:
        response = httpx.post(backend_url, json=data, headers=_auth_headers(), timeout=timeout)

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

        if response.status_code == 401:
            st.session_state["logged_in"] = False
            st.session_state["auth_token"] = ""
            st.warning("Session expired. Please log in again.")
            return None

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
    backend_url = f"{_get_backend_endpoint()}extract-pdf-text"
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

def check_backend(backend_endpoint):
    """Check backend reachability by hitting GET /v1/config. Returns config dict or None."""
    endpoint = (backend_endpoint or "").strip().rstrip("/")
    backend_url = f"{endpoint}/v1/config"
    try:
        response = httpx.get(backend_url, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def chat_with_tutor(
    chat_messages,
    learner_profile,
    *,
    goal_context=None,
    user_id=None,
    goal_id=None,
    session_index=None,
    learner_information="",
    return_metadata=False,
):
    data = {
        "messages": str(chat_messages),
        "learner_profile": str(learner_profile),
        "use_web_search": bool(use_search),
        "use_vector_retrieval": True,
        "use_media_search": True,
        "allow_preference_updates": True,
        "return_metadata": bool(return_metadata),
        "goal_context": _coerce_jsonable(goal_context),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    if isinstance(session_index, int) and session_index >= 0:
        data["session_index"] = session_index
    if learner_information is not None:
        data["learner_information"] = _normalize_learner_information(learner_information)

    mock_path = os.path.join(os.path.dirname(__file__), "../assets/data_example/ai)tutor_chat.json") if use_mock_data else None
    response = make_post_request(API_NAMES["chat_with_tutor"], data, mock_path)
    if not response:
        return None
    if return_metadata:
        return response
    return response.get("response")

def refine_learning_goal(learning_goal, learner_information):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
    }
    response = make_post_request(API_NAMES["refine_goal"], data)
    return response.get("refined_goal") if response else "Refined learning goal"


def identify_skill_gap(
    learning_goal,
    learner_information,
    user_id=None,
    goal_id=None,
):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    mock_path = os.path.join(os.path.dirname(__file__), "../assets/data_example/skill_gap.json") if use_mock_data else None
    response = make_post_request(API_NAMES["identify_skill_gap"], data, mock_path)
    if not response:
        return None, None, None, None
    return (
        response.get("skill_gaps"),
        response.get("goal_assessment"),
        response.get("retrieved_sources"),
        response.get("goal_context"),
    )


def audit_skill_gap_bias(skill_gaps_dict, learner_information):
    """Call the bias audit endpoint and return the audit result."""
    data = {
        "skill_gaps": json.dumps(skill_gaps_dict),
        "learner_information": _normalize_learner_information(learner_information),
    }
    return make_post_request(API_NAMES["audit_skill_gap_bias"], data)


def validate_profile_fairness(learner_profile, learner_information, persona_name=""):
    """Call the fairness validation endpoint and return the result."""
    data = {
        "learner_profile": json.dumps(learner_profile) if isinstance(learner_profile, dict) else str(learner_profile),
        "learner_information": _normalize_learner_information(learner_information),
        "persona_name": persona_name,
    }
    return make_post_request(API_NAMES["validate_profile_fairness"], data)


def audit_content_bias(generated_content, learner_information):
    """Call the content bias audit endpoint and return the audit result."""
    data = {
        "generated_content": str(generated_content),
        "learner_information": _normalize_learner_information(learner_information),
    }
    return make_post_request(API_NAMES["audit_content_bias"], data)


def audit_chatbot_bias(tutor_responses, learner_information):
    """Call the chatbot bias audit endpoint and return the audit result."""
    data = {
        "tutor_responses": str(tutor_responses),
        "learner_information": _normalize_learner_information(learner_information),
    }
    return make_post_request(API_NAMES["audit_chatbot_bias"], data)


def create_learner_profile(
    learning_goal,
    learner_information,
    skill_gaps,
    user_id=None,
    goal_id=None,
):
    data = {
        "learning_goal": str(learning_goal),
        "learner_information": _normalize_learner_information(learner_information),
        "skill_gaps": _normalize_skill_gaps(skill_gaps),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    mock_path = os.path.join(os.path.dirname(__file__), "../assets/data_example/learner_profile.json") if use_mock_data else None
    response = make_post_request(API_NAMES["create_profile"], data, mock_path)
    return response.get("learner_profile") if response else None

def update_learner_profile(learner_profile, learner_interactions, learner_information="", session_information="", user_id=None, goal_id=None):
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "learner_information": str(learner_information),
        "session_information": str(session_information),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    mock_path = os.path.join(os.path.dirname(__file__), "../assets/data_example/learner_profile.json") if use_mock_data else None
    response = make_post_request(API_NAMES["update_profile"], data, mock_path)
    return response.get("learner_profile") if response else None


def update_cognitive_status(learner_profile, session_information, user_id=None, goal_id=None):
    data = {
        "learner_profile": str(learner_profile),
        "session_information": str(session_information),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_cognitive_status"], data)
    return response.get("learner_profile") if response else None


def update_learning_preferences(learner_profile, learner_interactions, learner_information="", user_id=None, goal_id=None):
    data = {
        "learner_profile": str(learner_profile),
        "learner_interactions": str(learner_interactions),
        "learner_information": str(learner_information),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_learning_preferences"], data)
    return response.get("learner_profile") if response else None


def update_learner_information(
    learner_profile,
    edited_learner_information="",
    resume_text="",
    user_id=None,
    goal_id=None,
):
    data = {
        "learner_profile": str(learner_profile),
        "edited_learner_information": _normalize_learner_information(edited_learner_information),
        "resume_text": _normalize_learner_information(resume_text),
    }
    if user_id is not None:
        data["user_id"] = user_id
    if goal_id is not None:
        data["goal_id"] = goal_id
    response = make_post_request(API_NAMES["update_learner_information"], data)
    return response.get("learner_profile") if response else None


# @st.cache_resource
def schedule_learning_path(learner_profile, session_count=None):
    cfg = get_app_config()
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


def schedule_learning_path_agentic(learner_profile, session_count=None):
    """Call the agentic learning path endpoint with auto-refinement."""
    cfg = get_app_config()
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


def adapt_learning_path(user_id, goal_id, new_learner_profile=None, force=False):
    """Call the adaptive plan regeneration endpoint."""
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "force": bool(force),
    }
    if new_learner_profile is not None:
        data["new_learner_profile"] = str(new_learner_profile)
    response = make_post_request(API_NAMES["adapt_path"], data, timeout=120)
    if response:
        return {
            "learning_path": response.get("learning_path"),
            "agent_metadata": response.get("agent_metadata", {}),
            "adaptation": response.get("adaptation", {}),
        }
    return None

def generate_learning_content(
    learner_profile,
    learning_path,
    learning_session,
    use_search=True,
    allow_parallel=True,
    with_quiz=True,
    goal_context=None,
    user_id=None,
    goal_id=None,
    session_index=None,
):
    data = {
        "learner_profile": str(learner_profile),
        "learning_path": str(learning_path),
        "learning_session": str(learning_session),
        "use_search": bool(use_search),
        "allow_parallel": bool(allow_parallel),
        "with_quiz": bool(with_quiz),
        "goal_context": _coerce_jsonable(goal_context),
    }
    if user_id is not None:
        data["user_id"] = str(user_id)
    if goal_id is not None:
        data["goal_id"] = int(goal_id)
    if session_index is not None:
        data["session_index"] = int(session_index)
    mock_path = os.path.join(os.path.dirname(__file__), "../assets/data_example/learning_document.json") if use_mock_data else None
    response = make_post_request(API_NAMES["generate_learning_content"], data, mock_path)
    if not response:
        return None
    if isinstance(response, dict) and isinstance(response.get("learning_content"), dict):
        return response["learning_content"]
    return response if isinstance(response, dict) else None


def list_goals(user_id):
    url = f"{_get_backend_endpoint()}{API_NAMES['goals']}/{user_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json().get("goals", [])
    except Exception:
        pass
    return []


def create_goal(user_id, goal_payload):
    url = f"{_get_backend_endpoint()}{API_NAMES['goals']}/{user_id}"
    try:
        resp = httpx.post(url, json=_coerce_jsonable(goal_payload), headers=_auth_headers(), timeout=60)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def update_goal(user_id, goal_id, patch_payload):
    url = f"{_get_backend_endpoint()}{API_NAMES['goals']}/{user_id}/{goal_id}"
    try:
        resp = httpx.patch(url, json=_coerce_jsonable(patch_payload), headers=_auth_headers(), timeout=60)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def delete_goal(user_id, goal_id):
    url = f"{_get_backend_endpoint()}{API_NAMES['goals']}/{user_id}/{goal_id}"
    try:
        resp = httpx.delete(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_goal_runtime_state(user_id, goal_id):
    url = f"{_get_backend_endpoint()}{API_NAMES['goal_runtime_state']}/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_learning_content(user_id, goal_id, session_index, no_wait: bool = False):
    url = f"{_get_backend_endpoint()}{API_NAMES['learning_content_cache']}/{user_id}/{goal_id}/{session_index}"
    params = {"no_wait": "true"} if no_wait else {}
    try:
        resp = httpx.get(url, params=params, headers=_auth_headers(), timeout=60)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def delete_learning_content(user_id, goal_id, session_index):
    url = f"{_get_backend_endpoint()}{API_NAMES['learning_content_cache']}/{user_id}/{goal_id}/{session_index}"
    try:
        resp = httpx.delete(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def post_session_activity(user_id, goal_id, session_index, event_type, event_time=None):
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "session_index": int(session_index),
        "event_type": str(event_type),
    }
    if event_time is not None:
        data["event_time"] = str(event_time)
    response = make_post_request(API_NAMES["session_activity"], data)
    return response if response else None


def complete_session(user_id, goal_id, session_index, session_end_time=None):
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "session_index": int(session_index),
    }
    if session_end_time is not None:
        data["session_end_time"] = str(session_end_time)
    response = make_post_request(API_NAMES["complete_session"], data, timeout=120)
    return response if response else None


def propagate_learner_profile_to_other_goals(user_id: str, goal_id: int) -> None:
    """Push learning preferences and behavioral patterns from this goal to all other goals.

    Called after a user edits their FSLSM dimensions so the backend keeps all goals in sync.
    Best-effort: silently ignores errors (propagation failure is non-critical).
    """
    url = f"{_get_backend_endpoint()}propagate-profile/{user_id}/{goal_id}"
    try:
        httpx.post(url, headers=_auth_headers(), timeout=30)
    except Exception:
        pass


def submit_content_feedback(user_id, goal_id, feedback):
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "feedback": _coerce_jsonable(feedback),
    }
    response = make_post_request(API_NAMES["submit_content_feedback"], data, timeout=120)
    return response if response else None

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


def reset_mastery_attempt(user_id, goal_id, session_index):
    """Clear persisted mastery attempt for one session."""
    data = {
        "user_id": str(user_id),
        "goal_id": int(goal_id),
        "session_index": int(session_index),
    }
    response = make_post_request(API_NAMES["reset_mastery_attempt"], data)
    return response if response else None


def get_session_mastery_status(user_id, goal_id):
    """Get mastery status for all sessions in a goal."""
    url = f"{_get_backend_endpoint()}session-mastery-status/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_behavioral_metrics(user_id, goal_id=None):
    """Fetch computed behavioral metrics from the backend."""
    url = f"{_get_backend_endpoint()}behavioral-metrics/{user_id}"
    if goal_id is not None:
        url += f"?goal_id={goal_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def get_quiz_mix(user_id, goal_id, session_index):
    """Get SOLO-aligned question type counts for a session from the backend.

    Returns a dict with keys: single_choice_count, multiple_choice_count,
    true_false_count, short_answer_count, open_ended_count.
    Falls back to a standard beginner mix if the endpoint is unavailable.
    """
    url = f"{_get_backend_endpoint()}quiz-mix/{user_id}?goal_id={goal_id}&session_index={session_index}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    # Fallback: standard mix (same as previous hardcoded behaviour)
    return {
        "single_choice_count": 3,
        "multiple_choice_count": 1,
        "true_false_count": 1,
        "short_answer_count": 1,
        "open_ended_count": 0,
    }


def get_dashboard_metrics(user_id, goal_id):
    url = f"{_get_backend_endpoint()}{API_NAMES['dashboard_metrics']}/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def delete_user_data(backend_ep, user_id):
    """DELETE /user-data/{user_id} → (status_code, response_json)

    Clears all non-auth data: profiles (mastered skills, FSLSM, learner info),
    events, user state, and profile snapshots. Does NOT remove auth credentials.
    Used by Restart Onboarding.
    """
    if use_mock_data:
        return 200, {"ok": True}
    url = f"{backend_ep.rstrip('/')}/v1/user-data/{user_id}"
    try:
        resp = httpx.delete(url, headers=_auth_headers(), timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def auth_register(username, password):
    """Register a new user via the backend."""
    if use_mock_data:
        return 200, {"token": "mock-token", "username": username}
    data = {"username": username, "password": password}
    backend_url = f"{_get_backend_endpoint()}{API_NAMES['auth_register']}"
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
    backend_url = f"{_get_backend_endpoint()}{API_NAMES['auth_login']}"
    try:
        response = httpx.post(backend_url, json=data, timeout=30)
        return response.status_code, response.json()
    except Exception as e:
        return None, {"detail": str(e)}


def auth_delete_user(token):
    """Delete the authenticated user's account via DELETE /auth/user."""
    if use_mock_data:
        return 200, {"ok": True}
    url = f"{_get_backend_endpoint()}auth/user"
    try:
        resp = httpx.delete(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, {"detail": str(e)}


def sync_profile(user_id, goal_id):
    """Sync a goal's profile with shared fields from all other goals."""
    backend_url = f"{_get_backend_endpoint()}sync-profile/{user_id}/{goal_id}"
    try:
        response = httpx.post(backend_url, headers=_auth_headers(), timeout=30)
        if response.status_code == 200:
            return response.json().get("learner_profile")
    except Exception:
        pass
    return None


def get_learner_profile(user_id, goal_id):
    """Retrieve an existing learner profile from the backend store. Returns None if not found."""
    url = f"{_get_backend_endpoint()}profile/{user_id}?goal_id={goal_id}"
    try:
        resp = httpx.get(url, headers=_auth_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.json().get("learner_profile")
    except Exception:
        pass
    return None


def save_learner_profile(user_id, goal_id, learner_profile):
    """Persist a learner profile to the backend store without triggering an LLM call."""
    backend_url = f"{_get_backend_endpoint()}profile/{user_id}/{goal_id}"
    try:
        response = httpx.put(backend_url, json={"learner_profile": learner_profile}, headers=_auth_headers(), timeout=30)
        return response.status_code == 200
    except Exception:
        return False


def get_personas():
    """GET /personas → dict of personas. Falls back to local data on failure."""
    from utils.personas import PERSONAS as LOCAL_PERSONAS
    if use_mock_data:
        return LOCAL_PERSONAS
    url = f"{_get_backend_endpoint()}personas"
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
    url = f"{_get_backend_endpoint()}config"
    try:
        resp = httpx.get(url, timeout=30)
        if resp.status_code == 200:
            _cached_app_config = resp.json()
            return _cached_app_config
    except Exception:
        pass
    _cached_app_config = _LOCAL_APP_CONFIG
    return _cached_app_config
