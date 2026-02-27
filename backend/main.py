import os
import logging
import copy
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

os.environ.setdefault("USER_AGENT", "Ami/1.0 (educational-platform)")

_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
# Add to root so all module-level loggers (propagate=True by default) flow here.
# Uvicorn's own loggers have propagate=False so they are unaffected — no double-logging.
logging.root.addHandler(_handler)
logging.root.setLevel(logging.INFO)
# Allow DEBUG from our own code specifically.
logger = logging.getLogger("ami")
logger.setLevel(logging.DEBUG)

import ast
import json
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from io import BytesIO
import pdfplumber
from base.llm_factory import LLMFactory
from base.search_rag import SearchRagManager
from fastapi.responses import JSONResponse
from modules.skill_gap import *
from modules.learner_profiler import *
from modules.learning_plan_generator import *
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import (
    schedule_learning_path_agentic,
)
from modules.tools.learner_simulation_tool import create_simulate_feedback_tool
from modules.content_generator import *
from modules.content_generator.agents.content_feedback_simulator import simulate_content_feedback_with_llm
from modules.ai_chatbot_tutor import chat_with_tutor_with_llm
from api_schemas import *
from config import load_config
from utils import store
from utils import auth_store, auth_jwt
from utils.content_view import build_learning_content_view_model


app_config = load_config(config_name="main")
search_rag_manager = SearchRagManager.from_config(app_config)

app = FastAPI()

from fastapi import Request

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 500:
        # Recover the original exception via Python's implicit exception chaining.
        # When an endpoint does `except Exception as e: raise HTTPException(...)`,
        # the original exception is stored on exc.__context__ with its traceback intact.
        original = exc.__cause__ or exc.__context__
        if original and original.__traceback__:
            logger.error(
                "500 Internal Server Error on %s %s\n%s",
                request.method, request.url.path, exc.detail,
                exc_info=(type(original), original, original.__traceback__),
            )
        else:
            logger.error(
                "500 Internal Server Error on %s %s: %s",
                request.method, request.url.path, exc.detail,
            )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

from fastapi.staticfiles import StaticFiles
_BACKEND_ROOT = Path(__file__).resolve().parent
_AUDIO_DIR = _BACKEND_ROOT / "data" / "audio"
_DIAGRAMS_DIR = _BACKEND_ROOT / "data" / "diagrams"
_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/audio", StaticFiles(directory=str(_AUDIO_DIR)), name="audio")
_DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/diagrams", StaticFiles(directory=str(_DIAGRAMS_DIR)), name="diagrams")
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


@app.on_event("startup")
def _load_stores():
    store.load()
    auth_store.load()
    if search_rag_manager.verified_content_manager:
        search_rag_manager.verified_content_manager.sync_verified_content(
            app_config.get("verified_content", {}).get("base_dir", "resources/verified-course-content")
        )


def _parse_jsonish(value: Any, default: Any = None):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            try:
                return ast.literal_eval(text)
            except Exception:
                return default
    return value


def _compute_mastery_rate(profile: dict) -> float:
    if not isinstance(profile, dict):
        return 0.0
    cognitive = profile.get("cognitive_status", {})
    mastered = cognitive.get("mastered_skills", [])
    in_progress = cognitive.get("in_progress_skills", [])
    total = len(mastered) + len(in_progress)
    return round(len(mastered) / total, 4) if total > 0 else 0.0


def _refresh_goal_profile(user_id: str, goal_id: int) -> dict:
    merged = store.merge_shared_profile_fields(user_id, goal_id)
    return merged or store.get_profile(user_id, goal_id) or {}


def _goal_or_404(user_id: str, goal_id: int) -> dict:
    goal = store.get_goal(user_id, goal_id)
    if goal is None or goal.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _goal_aggregate_or_404(user_id: str, goal_id: int) -> dict:
    goal = store.get_goal_aggregate(user_id, goal_id)
    if goal is None or goal.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _parse_iso_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value).timestamp()
        return float(value)
    except Exception:
        return None


def _iso_from_ts(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _normalize_session_activity_record(activity: Optional[dict], idle_timeout_secs: int) -> dict:
    record = copy.deepcopy(activity) if isinstance(activity, dict) else {}
    record.setdefault("user_id", None)
    record.setdefault("goal_id", None)
    record.setdefault("session_index", None)
    record.setdefault("trigger_events", [])
    record.setdefault("heartbeats", [])
    record.setdefault("last_activity_at", None)

    intervals = record.get("intervals")
    if not isinstance(intervals, list):
        intervals = []

    # Backward compatibility for old single-span records.
    legacy_start = record.get("start_time")
    legacy_end = record.get("end_time")
    if not intervals and legacy_start is not None:
        intervals = [{"start_time": legacy_start, "end_time": legacy_end}]

    normalized_intervals = []
    for interval in intervals:
        if not isinstance(interval, dict):
            continue
        start = interval.get("start_time")
        if start is None:
            continue
        normalized_intervals.append({
            "start_time": start,
            "end_time": interval.get("end_time"),
        })

    record["intervals"] = normalized_intervals
    if record["last_activity_at"] is None and record["heartbeats"]:
        record["last_activity_at"] = record["heartbeats"][-1]
    if record["last_activity_at"] is None and normalized_intervals:
        record["last_activity_at"] = normalized_intervals[-1].get("end_time") or normalized_intervals[-1].get("start_time")

    if normalized_intervals:
        record["start_time"] = normalized_intervals[0].get("start_time")
        record["end_time"] = normalized_intervals[-1].get("end_time")
    else:
        record["start_time"] = None
        record["end_time"] = None

    return record


def _close_open_interval(record: dict, requested_end_time: Optional[str], idle_timeout_secs: int) -> dict:
    intervals = record.setdefault("intervals", [])
    if not intervals:
        return record
    current = intervals[-1]
    if current.get("end_time") is not None:
        return record

    requested_end_ts = _parse_iso_ts(requested_end_time) if requested_end_time else None
    last_activity_ts = _parse_iso_ts(record.get("last_activity_at"))
    end_ts = requested_end_ts if requested_end_ts is not None else last_activity_ts
    if requested_end_ts is not None and last_activity_ts is not None and requested_end_ts - last_activity_ts > idle_timeout_secs:
        end_ts = last_activity_ts
    if end_ts is None:
        end_ts = _parse_iso_ts(current.get("start_time"))
    current["end_time"] = _iso_from_ts(end_ts)
    record["end_time"] = current["end_time"]
    return record


def _sum_activity_duration_secs(activity: Optional[dict], idle_timeout_secs: int) -> float:
    record = _normalize_session_activity_record(activity, idle_timeout_secs)
    total = 0.0
    for interval in record.get("intervals", []):
        start_ts = _parse_iso_ts(interval.get("start_time"))
        end_ts = _parse_iso_ts(interval.get("end_time"))
        if start_ts is None or end_ts is None:
            continue
        total += max(end_ts - start_ts, 0.0)
    return total


def _build_goal_runtime_state(user_id: str, goal_id: int) -> dict:
    goal = _goal_or_404(user_id, goal_id)
    sessions = []
    learning_path = goal.get("learning_path", [])
    adaptation_suggested = False
    adaptation_message = None
    for idx, session in enumerate(learning_path):
        if not isinstance(session, dict):
            continue
        navigation_mode = session.get("navigation_mode", "linear")
        if navigation_mode == "free" or idx == 0:
            is_locked = False
        else:
            prev = learning_path[idx - 1] if idx - 1 < len(learning_path) else {}
            is_locked = not bool(prev.get("is_mastered", False))
        is_mastered = bool(session.get("is_mastered", False))
        if not is_mastered and session.get("mastery_score") is not None:
            threshold = session.get("mastery_threshold", APP_CONFIG["mastery_threshold_default"])
            if float(session.get("mastery_score", 0) or 0) < threshold * 0.8:
                adaptation_suggested = True
        can_complete = True
        completion_block_reason = None
        if navigation_mode == "linear" and not is_mastered:
            can_complete = False
            completion_block_reason = "session_not_mastered"
        sessions.append({
            "session_index": idx,
            "session_id": session.get("id", ""),
            "is_locked": is_locked,
            "can_open": not is_locked,
            "can_complete": can_complete,
            "completion_block_reason": completion_block_reason,
            "if_learned": bool(session.get("if_learned", False)),
            "is_mastered": is_mastered,
            "mastery_score": session.get("mastery_score"),
            "mastery_threshold": session.get("mastery_threshold", APP_CONFIG["mastery_threshold_default"]),
            "navigation_mode": navigation_mode,
        })
    if adaptation_suggested:
        adaptation_message = "Recent quiz performance suggests future sessions may need adjustment."
    return {
        "goal_id": goal_id,
        "adaptation": {
            "suggested": adaptation_suggested,
            "message": adaptation_message,
        },
        "sessions": sessions,
    }

class BehaviorEvent(BaseModel):
    user_id: str
    event_type: str
    payload: Dict[str, Any] = {}
    ts: Optional[str] = None

@app.post("/events/log")
async def log_event(evt: BehaviorEvent):
    e = evt.dict() if hasattr(evt, "dict") else evt.model_dump()
    e["ts"] = e["ts"] or datetime.utcnow().isoformat()
    store.append_event(evt.user_id, e)
    return {"ok": True, "event_count": len(store.get_events(evt.user_id))}

class AutoProfileUpdateRequest(BaseModel):
    user_id: str
    goal_id: int = 0

    # optional overrides (otherwise uses app_config defaults via get_llm)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None

    # only needed if this is the FIRST time we create the profile
    learning_goal: Optional[str] = None
    learner_information: Optional[Any] = None
    skill_gaps: Optional[Any] = None

    # optional session metadata
    session_information: Optional[Dict[str, Any]] = None


@app.post("/profile/auto-update")
async def auto_update_profile(request: AutoProfileUpdateRequest):
    """
    If profile doesn't exist: initialize it (needs learning_goal + learner_information + skill_gaps).
    If profile exists: update it using EVENT_STORE[user_id] as learner_interactions.
    """
    try:
        user_id = request.user_id
        llm = get_llm(request.model_provider, request.model_name)  # uses defaults if None

        goal_id = request.goal_id

        # grab recent events for this user (can be empty)
        interactions = store.get_events(user_id)

        # Normalize optional structured fields (match style used in /create-learner-profile-with-info)
        learner_info = request.learner_information
        if isinstance(learner_info, str):
            try:
                learner_info = ast.literal_eval(learner_info)
            except Exception:
                learner_info = {"raw": learner_info}

        skill_gaps = request.skill_gaps
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}

        # CASE A: first-time user => create profile
        if store.get_profile(user_id, goal_id) is None:
            if not (request.learning_goal and learner_info is not None and skill_gaps is not None):
                raise HTTPException(
                    status_code=400,
                    detail="No profile found for this user_id. Provide learning_goal, learner_information, and skill_gaps to initialize."
                )

            profile = initialize_learner_profile_with_llm(
                llm,
                request.learning_goal,
                learner_info,
                skill_gaps,
            )

            store.upsert_profile(user_id, goal_id, profile)
            return {
                "ok": True,
                "mode": "initialized",
                "user_id": user_id,
                "goal_id": goal_id,
                "event_count_used": len(interactions),
                "learner_profile": profile,
            }

        # CASE B: existing user => update profile from events
        current_profile = store.get_profile(user_id, goal_id)

        session_info = request.session_information or {}
        session_info = {
            **session_info,
            "updated_at": datetime.utcnow().isoformat(),
            "event_count": len(interactions),
            "source": "EVENT_STORE",
        }

        updated_profile = update_learner_profile_with_llm(
            llm,
            current_profile,
            interactions,
            learner_info if learner_info is not None else "",
            session_info,
        )

        store.upsert_profile(user_id, goal_id, updated_profile)

        return {
            "ok": True,
            "mode": "updated",
            "user_id": user_id,
            "goal_id": goal_id,
            "event_count_used": len(interactions),
            "learner_profile": updated_profile,
        }

    except HTTPException:
        raise
    except Exception as e:
        # Make Swagger show the real exception message
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync-profile/{user_id}/{goal_id}")
async def sync_profile(user_id: str, goal_id: int):
    """Merge shared profile fields (mastered skills, preferences, behavioral patterns)
    from all of a user's goals into the target goal's profile."""
    result = store.merge_shared_profile_fields(user_id, goal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No profile found for this goal")
    return {"learner_profile": result}


@app.put("/profile/{user_id}/{goal_id}")
async def put_profile(user_id: str, goal_id: int, body: dict):
    """Persist a learner profile to the store without an LLM call."""
    profile = body.get("learner_profile")
    if not profile:
        raise HTTPException(status_code=400, detail="learner_profile is required")
    store.upsert_profile(user_id, goal_id, profile)
    return {"ok": True}


@app.get("/profile/{user_id}")
async def get_profile(user_id: str, goal_id: Optional[int] = None):
    if goal_id is not None:
        profile = store.get_profile(user_id, goal_id)
        if not profile:
            raise HTTPException(status_code=404, detail="No profile found for this user_id and goal_id")
        return {"user_id": user_id, "goal_id": goal_id, "learner_profile": profile}
    profiles = store.get_all_profiles_for_user(user_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="No profile found for this user_id")
    return {"user_id": user_id, "profiles": profiles}

@app.get("/events/{user_id}")
async def get_events(user_id: str):
    return {"user_id": user_id, "events": store.get_events(user_id)}


@app.delete("/user-data/{user_id}")
async def delete_user_data(user_id: str):
    """Delete all non-auth data for a user (profiles, events, state, snapshots).
    Used by Restart Onboarding so mastered skills and persona info are fully cleared."""
    store.delete_all_user_data(user_id)
    return {"ok": True}


@app.get("/goals/{user_id}")
async def list_goals(user_id: str):
    return {"goals": store.list_goal_aggregates(user_id)}


@app.post("/goals/{user_id}")
async def create_goal(user_id: str, request: GoalCreateRequest):
    payload = request.model_dump()
    learner_profile = payload.pop("learner_profile", None)
    goal = store.create_goal(user_id, payload)
    if isinstance(learner_profile, dict) and learner_profile:
        store.upsert_profile(user_id, goal["id"], learner_profile)
    return store.get_goal_aggregate(user_id, goal["id"])


@app.patch("/goals/{user_id}/{goal_id}")
async def patch_goal(user_id: str, goal_id: int, request: GoalUpdateRequest):
    payload = {k: v for k, v in request.model_dump().items() if v is not None}
    goal = store.patch_goal(user_id, goal_id, payload)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return store.get_goal_aggregate(user_id, goal_id)


@app.delete("/goals/{user_id}/{goal_id}")
async def soft_delete_goal(user_id: str, goal_id: int):
    goal = store.delete_goal(user_id, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


@app.get("/goal-runtime-state/{user_id}")
async def goal_runtime_state(user_id: str, goal_id: int):
    return _build_goal_runtime_state(user_id, goal_id)


@app.get("/learning-content/{user_id}/{goal_id}/{session_index}")
async def get_learning_content(user_id: str, goal_id: int, session_index: int):
    record = store.get_learning_content(user_id, goal_id, session_index)
    if not record:
        raise HTTPException(status_code=404, detail="Learning content not found")
    return record.get("learning_content", {})


@app.delete("/learning-content/{user_id}/{goal_id}/{session_index}")
async def delete_learning_content(user_id: str, goal_id: int, session_index: int):
    store.delete_learning_content(user_id, goal_id, session_index)
    return {"ok": True}


@app.post("/session-activity")
async def session_activity(request: SessionActivityRequest):
    if request.event_type not in {"start", "heartbeat", "end"}:
        raise HTTPException(status_code=400, detail="Unsupported event_type")

    event_time = request.event_time or datetime.now(timezone.utc).isoformat()
    interval = APP_CONFIG["motivational_trigger_interval_secs"]
    activity = _normalize_session_activity_record(
        store.get_session_activity(request.user_id, request.goal_id, request.session_index) or {
        "user_id": request.user_id,
        "goal_id": request.goal_id,
        "session_index": request.session_index,
        "start_time": None,
        "end_time": None,
        "intervals": [],
        "heartbeats": [],
        "trigger_events": [],
        "last_activity_at": None,
    },
        interval,
    )

    trigger = {"show": False, "kind": None, "message": None}

    if request.event_type == "start":
        last_activity_ts = _parse_iso_ts(activity.get("last_activity_at"))
        current_ts = _parse_iso_ts(event_time)
        intervals = activity.setdefault("intervals", [])
        has_open_interval = bool(intervals and intervals[-1].get("end_time") is None)
        if has_open_interval and last_activity_ts is not None and current_ts is not None and (current_ts - last_activity_ts) > interval:
            _close_open_interval(activity, activity.get("last_activity_at"), interval)
            has_open_interval = False
        if not has_open_interval:
            intervals.append({"start_time": event_time, "end_time": None})
        activity["start_time"] = activity.get("start_time") or event_time
        activity["last_activity_at"] = event_time
        activity.setdefault("heartbeats", []).append(event_time)
    elif request.event_type == "heartbeat":
        heartbeats = activity.setdefault("heartbeats", [])
        activity["last_activity_at"] = event_time
        should_append = True
        if heartbeats:
            try:
                last = datetime.fromisoformat(heartbeats[-1]).timestamp()
                curr = datetime.fromisoformat(event_time).timestamp()
                should_append = (curr - last) >= interval
            except Exception:
                should_append = True
        if should_append:
            heartbeats.append(event_time)
            trigger_count = len(activity.setdefault("trigger_events", []))
            kind = "posture" if trigger_count % 2 == 0 else "encouragement"
            message = (
                "Stay hydrated and keep a healthy posture."
                if kind == "posture" else
                "Keep up the good work!"
            )
            activity["trigger_events"].append({"kind": kind, "time": event_time})
            trigger = {"show": True, "kind": kind, "message": message}
    else:
        _close_open_interval(activity, event_time, interval)

    if activity.get("intervals"):
        activity["start_time"] = activity["intervals"][0].get("start_time")
        activity["end_time"] = activity["intervals"][-1].get("end_time")
    store.upsert_session_activity(request.user_id, request.goal_id, request.session_index, activity)
    return {"ok": True, "trigger": trigger}


@app.post("/complete-session")
async def complete_session(request: CompleteSessionRequest):
    llm = get_llm(request.model_provider, request.model_name)
    goal = _goal_or_404(request.user_id, request.goal_id)
    learning_path = goal.get("learning_path", [])
    if request.session_index < 0 or request.session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[request.session_index]
    session["if_learned"] = True
    learning_path[request.session_index] = session
    store.patch_goal(request.user_id, request.goal_id, {"learning_path": learning_path})

    profile = store.get_profile(request.user_id, request.goal_id) or {}
    try:
        profile = update_cognitive_status_with_llm(llm, profile, session)
    except Exception:
        profile = update_learner_profile_with_llm(
            llm,
            profile,
            "Session completed. Update cognitive status only. Do NOT change learning_preferences or behavioral_patterns.",
            "",
            session,
        )
    store.upsert_profile(request.user_id, request.goal_id, profile)
    merged = _refresh_goal_profile(request.user_id, request.goal_id)
    store.append_mastery_history(request.user_id, request.goal_id, _compute_mastery_rate(merged))
    await session_activity(SessionActivityRequest(
        user_id=request.user_id,
        goal_id=request.goal_id,
        session_index=request.session_index,
        event_type="end",
        event_time=request.session_end_time,
    ))
    return {
        "ok": True,
        "goal": _goal_aggregate_or_404(request.user_id, request.goal_id),
        "learner_profile": merged,
        "updated_session": session,
        "goal_runtime_state": _build_goal_runtime_state(request.user_id, request.goal_id),
        "profile_sync_applied": True,
    }


@app.post("/submit-content-feedback")
async def submit_content_feedback(request: SubmitContentFeedbackRequest):
    llm = get_llm(request.model_provider, request.model_name)
    feedback = _parse_jsonish(request.feedback, request.feedback)
    profile = store.get_profile(request.user_id, request.goal_id) or {}
    store.save_profile_snapshot(request.user_id, request.goal_id, profile)
    profile = update_learning_preferences_with_llm(llm, profile, feedback, "")
    store.upsert_profile(request.user_id, request.goal_id, profile)
    merged = _refresh_goal_profile(request.user_id, request.goal_id)
    return {
        "ok": True,
        "goal": _goal_aggregate_or_404(request.user_id, request.goal_id),
        "learner_profile": merged,
        "goal_runtime_state": _build_goal_runtime_state(request.user_id, request.goal_id),
        "profile_sync_applied": True,
    }


@app.get("/dashboard-metrics/{user_id}")
async def dashboard_metrics(user_id: str, goal_id: int):
    goal = _goal_aggregate_or_404(user_id, goal_id)
    profile = goal.get("learner_profile", {})
    metrics = await get_behavioral_metrics(user_id, goal_id=goal_id)
    skill_levels = APP_CONFIG["skill_levels"]
    level_map = {name: idx for idx, name in enumerate(skill_levels)}
    mastered = profile.get("cognitive_status", {}).get("mastered_skills", [])
    in_progress = profile.get("cognitive_status", {}).get("in_progress_skills", [])
    skills = [
        {
            "name": skill.get("name", ""),
            "required_level": skill.get("proficiency_level", "unlearned"),
            "current_level": skill.get("proficiency_level", "unlearned"),
        }
        for skill in mastered
    ] + [
        {
            "name": skill.get("name", ""),
            "required_level": skill.get("required_proficiency_level", "unlearned"),
            "current_level": skill.get("current_proficiency_level", "unlearned"),
        }
        for skill in in_progress
    ]
    session_series = []
    idle_timeout = APP_CONFIG["motivational_trigger_interval_secs"]
    for idx, session in enumerate(goal.get("learning_path", [])):
        activity = store.get_session_activity(user_id, goal_id, idx) or {}
        time_spent_min = _sum_activity_duration_secs(activity, idle_timeout) / 60.0
        session_series.append({"session_id": session.get("id", f"session-{idx}"), "time_spent_min": time_spent_min})
    history = store.get_mastery_history(user_id, goal_id)
    mastery_series = [{"sample_index": idx, "mastery_rate": item.get("mastery_rate", 0.0)} for idx, item in enumerate(history)]
    return {
        "goal_id": goal_id,
        "overall_progress": profile.get("cognitive_status", {}).get("overall_progress", 0.0),
        "skill_radar": {
            "labels": [skill["name"] for skill in skills],
            "current_levels": [level_map.get(skill["current_level"], 0) for skill in skills],
            "required_levels": [level_map.get(skill["required_level"], 0) for skill in skills],
            "skill_levels": skill_levels,
        },
        "session_time_series": session_series,
        "mastery_time_series": mastery_series,
        "behavioral_metrics": metrics,
    }


@app.get("/behavioral-metrics/{user_id}")
async def get_behavioral_metrics(user_id: str, goal_id: Optional[int] = None):
    goals = store.get_all_goals_for_user(user_id)
    if not goals:
        raise HTTPException(status_code=404, detail="No goals found for this user_id")

    completed = []
    total_triggers = 0
    idle_timeout = APP_CONFIG["motivational_trigger_interval_secs"]
    for goal in goals:
        gid = goal.get("id")
        if goal_id is not None and gid != goal_id:
            continue
        for idx, _session in enumerate(goal.get("learning_path", [])):
            times = store.get_session_activity(user_id, gid, idx)
            if not isinstance(times, dict):
                continue
            duration = _sum_activity_duration_secs(times, idle_timeout)
            if duration > 0:
                completed.append(duration)
            triggers = times.get("trigger_events", [])
            if isinstance(triggers, list):
                total_triggers += len(triggers)

    total_in_path = 0
    sessions_learned = 0
    if goal_id is not None:
        for g in goals:
            if isinstance(g, dict) and g.get("id") == goal_id:
                path = g.get("learning_path", [])
                total_in_path = len(path)
                sessions_learned = sum(1 for s in path if isinstance(s, dict) and s.get("if_learned"))
                break

    history = store.get_mastery_history(user_id, goal_id) if goal_id is not None else []
    history_rates = [float(item.get("mastery_rate", 0.0)) for item in history if isinstance(item, dict)]

    total_duration = sum(completed)
    avg_duration = total_duration / len(completed) if completed else 0.0

    return {
        "user_id": user_id,
        "goal_id": goal_id,
        "sessions_completed": len(completed),
        "total_sessions_in_path": total_in_path,
        "sessions_learned": sessions_learned,
        "avg_session_duration_sec": round(avg_duration, 1),
        "total_learning_time_sec": round(total_duration, 1),
        "motivational_triggers_count": total_triggers,
        "mastery_history": history_rates,
        "latest_mastery_rate": history_rates[-1] if history_rates else None,
    }


@app.post("/evaluate-mastery")
async def evaluate_mastery(request: MasteryEvaluationRequest):
    """Evaluate quiz answers, compute score, and determine mastery status."""
    from utils.quiz_scorer import compute_quiz_score, get_mastery_threshold_for_session
    from utils.solo_evaluator import evaluate_free_text_response, evaluate_short_answer_response

    goal = _goal_or_404(request.user_id, request.goal_id)

    learning_path = goal.get("learning_path", [])
    if request.session_index < 0 or request.session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[request.session_index]

    # Retrieve cached quiz data
    cached = store.get_learning_content(request.user_id, request.goal_id, request.session_index) or {}
    quiz_data = (cached.get("learning_content") or {}).get("quizzes")
    if not quiz_data:
        raise HTTPException(status_code=404, detail="No quiz data found for this session")

    # LLM evaluation for free-text question types
    llm_evaluations: Dict[str, Any] = {}
    short_answer_feedback: List[Dict[str, Any]] = []
    open_ended_feedback: List[Dict[str, Any]] = []

    short_answer_qs = quiz_data.get("short_answer_questions", [])
    short_answer_answers = request.quiz_answers.get("short_answer_questions", [])
    if short_answer_qs and any(a is not None for a in short_answer_answers):
        llm = get_llm()
        for i, q in enumerate(short_answer_qs):
            student_ans = short_answer_answers[i] if i < len(short_answer_answers) else None
            if student_ans is None:
                short_answer_feedback.append({"is_correct": False, "feedback": "No answer provided."})
            else:
                try:
                    is_correct, feedback = evaluate_short_answer_response(
                        llm, q["question"], q["expected_answer"], str(student_ans)
                    )
                    short_answer_feedback.append({"is_correct": is_correct, "feedback": feedback})
                except Exception:
                    # Fallback to exact match on LLM error
                    is_correct = str(student_ans).strip().lower() == q["expected_answer"].strip().lower()
                    short_answer_feedback.append({"is_correct": is_correct, "feedback": ""})
        llm_evaluations["short_answer_evaluations"] = short_answer_feedback

    open_ended_qs = quiz_data.get("open_ended_questions", [])
    open_ended_answers = request.quiz_answers.get("open_ended_questions", [])
    if open_ended_qs and any(a is not None for a in open_ended_answers):
        llm = get_llm()
        for i, q in enumerate(open_ended_qs):
            student_ans = open_ended_answers[i] if i < len(open_ended_answers) else None
            if student_ans is None:
                open_ended_feedback.append({
                    "solo_level": "prestructural",
                    "score": 0.0,
                    "feedback": "No answer provided.",
                })
            else:
                try:
                    evaluation = evaluate_free_text_response(
                        llm,
                        q["question"],
                        q["rubric"],
                        q["example_answer"],
                        str(student_ans),
                    )
                    open_ended_feedback.append(evaluation.model_dump())
                except Exception:
                    open_ended_feedback.append({
                        "solo_level": "prestructural",
                        "score": 0.0,
                        "feedback": "Evaluation unavailable.",
                    })
        llm_evaluations["open_ended_evaluations"] = open_ended_feedback

    # Score (passing llm_evaluations for semantic short-answer and open-ended scoring)
    correct, total, score_pct = compute_quiz_score(
        quiz_data,
        request.quiz_answers,
        llm_evaluations if llm_evaluations else None,
    )

    # Determine threshold
    threshold = get_mastery_threshold_for_session(
        session, APP_CONFIG["mastery_threshold_by_proficiency"],
        default=APP_CONFIG["mastery_threshold_default"],
    )

    is_mastered = score_pct >= threshold

    # Update session in goal store
    session["mastery_score"] = round(score_pct, 1)
    session["is_mastered"] = is_mastered
    session["mastery_threshold"] = threshold
    learning_path[request.session_index] = session
    store.patch_goal(request.user_id, request.goal_id, {"learning_path": learning_path})
    profile = store.get_profile(request.user_id, request.goal_id) or {}
    store.append_mastery_history(request.user_id, request.goal_id, _compute_mastery_rate(profile))

    # Flag adaptation suggestion if score is significantly below threshold
    plan_adaptation_suggested = (not is_mastered) and (score_pct < threshold * 0.8)

    response: Dict[str, Any] = {
        "score_percentage": round(score_pct, 1),
        "is_mastered": is_mastered,
        "threshold": threshold,
        "correct_count": correct,
        "total_count": total,
        "session_id": session.get("id", ""),
        "plan_adaptation_suggested": plan_adaptation_suggested,
    }
    if short_answer_feedback:
        response["short_answer_feedback"] = short_answer_feedback
    if open_ended_feedback:
        response["open_ended_feedback"] = open_ended_feedback
    return response


@app.get("/quiz-mix/{user_id}")
async def get_quiz_mix(user_id: str, goal_id: int, session_index: int):
    """Return the question type counts for a session based on its proficiency level."""
    from utils.quiz_scorer import get_quiz_mix_for_session

    goal = _goal_or_404(user_id, goal_id)

    learning_path = goal.get("learning_path", [])
    if session_index < 0 or session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[session_index]
    mix = get_quiz_mix_for_session(session, APP_CONFIG["quiz_mix_by_proficiency"])
    return mix


@app.get("/session-mastery-status/{user_id}")
async def session_mastery_status(user_id: str, goal_id: int):
    """Return mastery status for all sessions in a goal."""
    goal = _goal_or_404(user_id, goal_id)

    result = []
    for session in goal.get("learning_path", []):
        result.append({
            "session_id": session.get("id", ""),
            "is_mastered": session.get("is_mastered", False),
            "mastery_score": session.get("mastery_score"),
            "mastery_threshold": session.get("mastery_threshold", APP_CONFIG["mastery_threshold_default"]),
            "if_learned": session.get("if_learned", False),
        })

    return result


class AdaptLearningPathRequest(BaseRequest):
    """Request for adaptive plan regeneration."""
    user_id: str
    goal_id: int
    new_learner_profile: str


@app.post("/adapt-learning-path")
async def adapt_learning_path(request: AdaptLearningPathRequest):
    """Detect preference/mastery changes and adapt the learning path accordingly."""
    from modules.tools.plan_regeneration_tool import (
        compute_fslsm_deltas,
        decide_regeneration,
    )

    llm = get_llm(request.model_provider, request.model_name)

    try:
        new_profile = request.new_learner_profile
        if isinstance(new_profile, str) and new_profile.strip():
            new_profile = ast.literal_eval(new_profile)
        if not isinstance(new_profile, dict):
            new_profile = {}

        goal = _goal_or_404(request.user_id, request.goal_id)

        current_plan = {"learning_path": goal.get("learning_path", [])}
        # old_profile: use snapshot (pre-update) if available; fall back to current store
        old_profile = store.get_profile_snapshot(request.user_id, request.goal_id) or \
                      store.get_profile(request.user_id, request.goal_id) or {}

        # Extract FSLSM dimensions
        old_fslsm = (
            old_profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        new_fslsm = (
            new_profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )

        # Gather mastery results from the learning path
        mastery_results = []
        for i, session in enumerate(current_plan.get("learning_path", [])):
            if session.get("mastery_score") is not None:
                mastery_results.append({
                    "session_index": i,
                    "session_id": session.get("id", ""),
                    "score": session.get("mastery_score"),
                    "is_mastered": session.get("is_mastered", False),
                    "threshold": session.get("mastery_threshold", APP_CONFIG["mastery_threshold_default"]),
                })

        # Deterministic decision
        decision = decide_regeneration(
            current_plan, old_fslsm, new_fslsm, mastery_results,
        )

        result_plan = current_plan
        agent_metadata = {
            "decision": decision.model_dump(),
            "fslsm_deltas": compute_fslsm_deltas(old_fslsm, new_fslsm),
            "mastery_results": mastery_results,
        }

        if decision.action == "keep":
            store.delete_profile_snapshot(request.user_id, request.goal_id)
            return {**result_plan, "agent_metadata": agent_metadata}

        if decision.action == "adjust_future":
            # Reschedule only future sessions
            result_plan = reschedule_learning_path_with_llm(
                llm,
                current_plan.get("learning_path", []),
                new_profile,
                other_feedback=f"Adaptation reason: {decision.reason}",
            )

        elif decision.action == "regenerate":
            # Full agentic regeneration preserving learned sessions
            plan, regen_metadata = schedule_learning_path_agentic(
                llm, new_profile,
            )
            # Preserve learned sessions from original plan
            learned = [
                s for s in current_plan.get("learning_path", [])
                if s.get("if_learned", False)
            ]
            new_sessions = [
                s for s in plan.get("learning_path", [])
                if not s.get("if_learned", False)
            ]
            # Renumber new session IDs to avoid collisions with learned sessions
            learned_ids = {s.get("id") for s in learned}
            offset = len(learned)
            for i, s in enumerate(new_sessions):
                new_id = f"Session {offset + i + 1}"
                # Avoid collisions if IDs happen to overlap
                while new_id in learned_ids:
                    offset += 1
                    new_id = f"Session {offset + i + 1}"
                s["id"] = new_id
            result_plan = {"learning_path": learned + new_sessions}
            agent_metadata.update(regen_metadata)

        # Run a single evaluation pass on the adapted plan
        sim_tool = create_simulate_feedback_tool(llm, use_ground_truth=False)
        sim_feedback = sim_tool.invoke({
            "learning_path": result_plan.get("learning_path", []),
            "learner_profile": new_profile,
        })
        agent_metadata["evaluation_feedback"] = sim_feedback
        if not isinstance(sim_feedback, dict):
            sim_feedback = {}
        agent_metadata["evaluation"] = {
            "pass": sim_feedback.get("is_acceptable", True),
            "issues": sim_feedback.get("issues", []),
            "feedback_summary": sim_feedback.get("feedback", {}),
        }

        store.patch_goal(request.user_id, request.goal_id, {"learning_path": result_plan.get("learning_path", [])})
        store.delete_profile_snapshot(request.user_id, request.goal_id)
        return {**result_plan, "agent_metadata": agent_metadata}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/register")
async def auth_register(request: AuthRegisterRequest):
    if len(request.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        auth_store.create_user(request.username, request.password)
    except ValueError:
        raise HTTPException(status_code=409, detail="Username already exists")
    token = auth_jwt.create_token(request.username)
    return {"token": token, "username": request.username}


@app.post("/auth/login")
async def auth_login(request: AuthLoginRequest):
    if not auth_store.verify_password(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth_jwt.create_token(request.username)
    return {"token": token, "username": request.username}


@app.get("/auth/me")
async def auth_me(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    username = auth_jwt.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"username": username}


@app.delete("/auth/user")
async def auth_delete_user(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    username = auth_jwt.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not auth_store.delete_user(username):
        raise HTTPException(status_code=404, detail="User not found")
    store.delete_all_user_data(username)
    return {"ok": True}


def get_llm(model_provider: str | None = None, model_name: str | None = None, **kwargs):
    model_provider = model_provider or app_config.llm.provider
    model_name = model_name or app_config.llm.model_name
    return LLMFactory.create(model=model_name, model_provider=model_provider, **kwargs)

PERSONAS = {
    "Hands-on Explorer": {
        "description": "Prefers active experimentation, concrete examples, visual aids, and step-by-step guidance.",
        "fslsm_dimensions": {
            "fslsm_processing": -0.7,
            "fslsm_perception": -0.5,
            "fslsm_input": -0.5,
            "fslsm_understanding": -0.5,
        },
    },
    "Reflective Reader": {
        "description": "Prefers observation-based learning, abstract concepts, text-heavy materials, and big-picture overviews.",
        "fslsm_dimensions": {
            "fslsm_processing": 0.7,
            "fslsm_perception": 0.5,
            "fslsm_input": 0.7,
            "fslsm_understanding": 0.5,
        },
    },
    "Visual Learner": {
        "description": "Strongly prefers diagrams, videos, and visual aids with a slight preference for hands-on activities.",
        "fslsm_dimensions": {
            "fslsm_processing": -0.2,
            "fslsm_perception": -0.3,
            "fslsm_input": -0.8,
            "fslsm_understanding": -0.3,
        },
    },
    "Conceptual Thinker": {
        "description": "Prefers abstract theories, reflective analysis, and big-picture understanding.",
        "fslsm_dimensions": {
            "fslsm_processing": 0.5,
            "fslsm_perception": 0.7,
            "fslsm_input": 0.0,
            "fslsm_understanding": 0.7,
        },
    },
    "Balanced Learner": {
        "description": "No strong preference — adapts to any learning style. A neutral starting point.",
        "fslsm_dimensions": {
            "fslsm_processing": 0.0,
            "fslsm_perception": 0.0,
            "fslsm_input": 0.0,
            "fslsm_understanding": 0.0,
        },
    },
}


@app.get("/personas")
async def get_personas():
    """Return all available learning personas with their FSLSM dimensions."""
    return {"personas": PERSONAS}


APP_CONFIG = {
    "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
    "default_session_count": 8,
    "default_llm_type": "gpt4o",
    "default_method_name": "ami",
    "motivational_trigger_interval_secs": 180,
    "max_refinement_iterations": 5,
    "mastery_threshold_default": 70,
    "mastery_threshold_by_proficiency": {
        "beginner": 60,
        "intermediate": 70,
        "advanced": 80,
        "expert": 90,
    },
    "quiz_mix_by_proficiency": {
        "beginner": {
            "single_choice_count": 4,
            "multiple_choice_count": 0,
            "true_false_count": 1,
            "short_answer_count": 0,
            "open_ended_count": 0,
        },
        "intermediate": {
            "single_choice_count": 2,
            "multiple_choice_count": 2,
            "true_false_count": 1,
            "short_answer_count": 0,
            "open_ended_count": 0,
        },
        "advanced": {
            "single_choice_count": 1,
            "multiple_choice_count": 1,
            "true_false_count": 0,
            "short_answer_count": 2,
            "open_ended_count": 1,
        },
        "expert": {
            "single_choice_count": 0,
            "multiple_choice_count": 1,
            "true_false_count": 0,
            "short_answer_count": 1,
            "open_ended_count": 3,
        },
    },
    "fslsm_activation_threshold": 0.7,
    "fslsm_thresholds": {
        "perception": {
            "low_threshold": -0.7,
            "high_threshold": 0.7,
            "low_label": "Concrete examples and practical applications",
            "high_label": "Conceptual and theoretical explanations",
            "neutral_label": "A mix of practical and conceptual content",
        },
        "understanding": {
            "low_threshold": -0.7,
            "high_threshold": 0.7,
            "low_label": "presented in step-by-step sequences",
            "high_label": "with big-picture overviews first",
            "neutral_label": "balancing sequential detail and big-picture context",
        },
        "processing": {
            "low_threshold": -0.7,
            "high_threshold": 0.7,
            "low_label": "Hands-on and interactive activities",
            "high_label": "Reading and observation-based learning",
            "neutral_label": "A balance of interactive and reflective activities",
        },
        "input": {
            "low_threshold": -0.7,
            "high_threshold": 0.7,
            "low_label": "with diagrams, charts, and videos",
            "high_label": "with text-based materials and lectures",
            "neutral_label": "using both visual and verbal materials",
        },
    },
}


@app.get("/config")
async def get_app_config():
    """Return application configuration for frontend consumption."""
    return APP_CONFIG


@app.post("/extract-pdf-text")
async def extract_pdf_text(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF file."""
    try:
        contents = await file.read()
        with pdfplumber.open(BytesIO(contents)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return {"text": text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/list-llm-models")
async def list_llm_models():
    try:
        return {"models": [
            {
                "model_name": app_config.llm.model_name, 
                "model_provider": app_config.llm.provider
            }
        ]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})
        response = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=search_rag_manager,
            use_search=True,
        )
        return {"response": response}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/refine-learning-goal")
async def refine_learning_goal(request: LearningGoalRefinementRequest):
    llm = get_llm(request.model_provider, request.model_name)
    try:
        refined_learning_goal = refine_learning_goal_with_llm(llm, request.learning_goal, request.learner_information)
        return refined_learning_goal
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.post("/identify-skill-gap-with-info")
async def identify_skill_gap_with_info(request: SkillGapIdentificationRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learning_goal = request.learning_goal
    learner_information = request.learner_information
    skill_requirements = request.skill_requirements
    try:
        if isinstance(skill_requirements, str) and skill_requirements.strip():
            skill_requirements = ast.literal_eval(skill_requirements)
        if not isinstance(skill_requirements, dict):
            skill_requirements = None
        skill_gaps, skill_requirements = identify_skill_gap_with_llm(
            llm, learning_goal, learner_information, skill_requirements,
            search_rag_manager=search_rag_manager,
        )
        results = {**skill_gaps, **skill_requirements}
        return results
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/audit-skill-gap-bias")
async def audit_skill_gap_bias(request: BiasAuditRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_information = request.learner_information
    skill_gaps = request.skill_gaps
    try:
        if isinstance(skill_gaps, str) and skill_gaps.strip():
            try:
                skill_gaps = json.loads(skill_gaps)
            except json.JSONDecodeError:
                skill_gaps = ast.literal_eval(skill_gaps)
        if not isinstance(skill_gaps, dict):
            skill_gaps = {"skill_gaps": []}
        result = audit_skill_gap_bias_with_llm(llm, learner_information, skill_gaps)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/create-learner-profile-with-info")
async def create_learner_profile_with_info(request: LearnerProfileInitializationWithInfoRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_information = request.learner_information
    learning_goal = request.learning_goal
    skill_gaps = request.skill_gaps
    try:
        if isinstance(learner_information, str):
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        if isinstance(skill_gaps, str):
            try:
                skill_gaps = ast.literal_eval(skill_gaps)
            except Exception:
                skill_gaps = {"raw": skill_gaps}
        learner_profile = initialize_learner_profile_with_llm(
            llm, learning_goal, learner_information, skill_gaps
        )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validate-profile-fairness")
async def validate_profile_fairness(request: ProfileFairnessRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_information = request.learner_information
    persona_name = request.persona_name
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            try:
                learner_profile = json.loads(learner_profile)
            except json.JSONDecodeError:
                learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        result = validate_profile_fairness_with_llm(
            llm, learner_information, learner_profile, persona_name
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/update-learner-profile")
async def update_learner_profile(request: LearnerProfileUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    learner_information = request.learner_information
    session_information = request.session_information
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            try:
                learner_profile = ast.literal_eval(learner_profile)
            except Exception:
                learner_profile = {"raw": learner_profile}
        if isinstance(learner_interactions, str) and learner_interactions.strip():
            try:
                learner_interactions = ast.literal_eval(learner_interactions)
            except Exception:
                learner_interactions = {"raw": learner_interactions}
        if isinstance(learner_information, str) and learner_information.strip():
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        if isinstance(session_information, str) and session_information.strip():
            try:
                session_information = ast.literal_eval(session_information)
            except Exception:
                pass
        # Snapshot the pre-update FSLSM state so adapt-learning-path can compare old vs new.
        if request.user_id is not None and request.goal_id is not None and isinstance(learner_profile, dict):
            store.save_profile_snapshot(request.user_id, request.goal_id, learner_profile)
        learner_profile = update_learner_profile_with_llm(
            llm,
            learner_profile,
            learner_interactions,
            learner_information,
            session_information,
        )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-cognitive-status")
async def update_cognitive_status(request: CognitiveStatusUpdateRequest):
    import traceback as _tb
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_information = request.session_information
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            try:
                learner_profile = ast.literal_eval(learner_profile)
            except Exception:
                learner_profile = {"raw": learner_profile}
        if isinstance(session_information, str) and session_information.strip():
            try:
                session_information = ast.literal_eval(session_information)
            except Exception:
                pass
        try:
            learner_profile = update_cognitive_status_with_llm(
                llm,
                learner_profile,
                session_information,
            )
        except Exception as llm_err:
            print(f"[update-cognitive-status] Scoped update failed: {llm_err}")
            _tb.print_exc()
            # Fallback to the general update function which is known to work
            learner_profile = update_learner_profile_with_llm(
                llm,
                learner_profile,
                "Session completed. Update cognitive status only. Do NOT change learning_preferences or behavioral_patterns.",
                "",
                session_information,
            )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update-learning-preferences")
async def update_learning_preferences(request: LearningPreferencesUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learner_interactions = request.learner_interactions
    learner_information = request.learner_information
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            try:
                learner_profile = ast.literal_eval(learner_profile)
            except Exception:
                learner_profile = {"raw": learner_profile}
        if isinstance(learner_interactions, str) and learner_interactions.strip():
            try:
                learner_interactions = ast.literal_eval(learner_interactions)
            except Exception:
                learner_interactions = {"raw": learner_interactions}
        if isinstance(learner_information, str) and learner_information.strip():
            try:
                learner_information = ast.literal_eval(learner_information)
            except Exception:
                learner_information = {"raw": learner_information}
        # Snapshot the pre-update FSLSM state so adapt-learning-path can compare old vs new.
        if request.user_id is not None and request.goal_id is not None and isinstance(learner_profile, dict):
            store.save_profile_snapshot(request.user_id, request.goal_id, learner_profile)
        learner_profile = update_learning_preferences_with_llm(
            llm,
            learner_profile,
            learner_interactions,
            learner_information,
        )
        if request.user_id is not None and request.goal_id is not None:
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/schedule-learning-path")
async def schedule_learning_path(request: LearningPathSchedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_count = request.session_count
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        learning_path = schedule_learning_path_with_llm(
            llm, learner_profile, session_count,
        )
        return learning_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reschedule-learning-path")
async def reschedule_learning_path(request: LearningPathReschedulingRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    session_count = request.session_count
    other_feedback = request.other_feedback
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        if isinstance(learning_path, str) and learning_path.strip():
            learning_path = ast.literal_eval(learning_path)
        if isinstance(other_feedback, str) and other_feedback.strip():
            try:
                other_feedback = ast.literal_eval(other_feedback)
            except Exception:
                pass
        learning_path_result = reschedule_learning_path_with_llm(
            llm, learning_path, learner_profile, session_count, other_feedback,
        )
        return learning_path_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AgenticLearningPathRequest(BaseRequest):
    """Request for agentic learning path generation with auto-refinement."""
    learner_profile: str
    session_count: int = 0


@app.post("/schedule-learning-path-agentic")
async def schedule_learning_path_agentic_endpoint(request: AgenticLearningPathRequest):
    """Agentic learning path generation with retrieval, simulation, and auto-refinement."""
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    session_count = request.session_count
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if not isinstance(learner_profile, dict):
            learner_profile = {}
        plan, agent_metadata = schedule_learning_path_agentic(
            llm, learner_profile, session_count,
        )
        return {
            **plan,
            "agent_metadata": agent_metadata,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/draft-knowledge-point")
async def draft_knowledge_point(request: KnowledgePointDraftingRequest):
    from modules.content_generator.utils import (
        build_session_adaptation_contract,
        get_fslsm_dim,
        get_fslsm_input,
        processing_perception_hints,
        visual_formatting_hints,
    )
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_point = request.knowledge_point
    use_search = request.use_search
    goal_context = request.goal_context
    fslsm_input = get_fslsm_input(learner_profile)
    fslsm_processing = get_fslsm_dim(learner_profile, "fslsm_processing")
    fslsm_perception = get_fslsm_dim(learner_profile, "fslsm_perception")
    visual_hints = visual_formatting_hints(fslsm_input)
    proc_perc_hints = processing_perception_hints(fslsm_processing, fslsm_perception)
    session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
    try:
        knowledge_draft = draft_knowledge_point_with_llm(
            llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_point,
            use_search,
            goal_context=goal_context,
            visual_formatting_hints=visual_hints,
            processing_perception_hints=proc_perc_hints,
            session_adaptation_contract=session_adaptation_contract,
            search_rag_manager=search_rag_manager,
        )
        return {"knowledge_draft": knowledge_draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-learning-content")
async def generate_learning_content(request: LearningContentGenerationRequest):
    if request.method_name != "ami":
        raise HTTPException(status_code=400, detail="Unsupported method_name. Expected 'ami'.")

    llm = get_llm(request.model_provider, request.model_name)
    learning_path = request.learning_path
    learner_profile = request.learner_profile
    learning_session = request.learning_session
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    goal_context = request.goal_context

    try:
        learning_content = generate_learning_content_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            allow_parallel=allow_parallel,
            with_quiz=with_quiz,
            use_search=use_search,
            goal_context=goal_context,
            quiz_mix_config=APP_CONFIG["quiz_mix_by_proficiency"],
            method_name=request.method_name,
            search_rag_manager=search_rag_manager,
        )
        learning_content["view_model"] = build_learning_content_view_model(
            learning_content.get("document", ""),
            learning_content.get("sources_used", []),
            content_format=learning_content.get("content_format", "standard"),
            audio_mode=learning_content.get("audio_mode"),
        )
        if request.user_id is not None and request.goal_id is not None and request.session_index is not None:
            store.upsert_learning_content(
                request.user_id,
                request.goal_id,
                request.session_index,
                learning_content,
            )
        return learning_content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/simulate-content-feedback")
async def simulate_content_feedback(request: LearningContentFeedbackRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    learning_content = request.learning_content
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            learner_profile = ast.literal_eval(learner_profile)
        if isinstance(learning_content, str) and learning_content.strip():
            learning_content = ast.literal_eval(learning_content)
        feedback = simulate_content_feedback_with_llm(llm, learner_profile, learning_content)
        return {"feedback": feedback}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    server_cfg = app_config.get("server", {})
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = int(app_config.get("server", {}).get("port", 8000))
    log_level = str(app_config.get("log_level", "debug")).lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
