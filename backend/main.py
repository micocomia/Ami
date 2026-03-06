import asyncio
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
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.root.setLevel(_log_level)
# Allow DEBUG from our own code specifically.
logger = logging.getLogger("ami")
logger.setLevel(logging.DEBUG)

import ast
import json
import threading
import time
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
from modules.learner_profiler.utils import fslsm_adaptation
from modules.learner_profiler.utils.behavioral_metrics import compute_behavioral_metrics
from modules.learner_profiler.utils.auto_update import auto_update_learner_profile
from modules.learner_profiler.utils.profile_edit_inputs import extract_slider_override_dims
from modules.learning_plan_generator import *
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import (
    evaluate_plan,
    schedule_learning_path_agentic,
)
from modules.learning_plan_generator.orchestrators.adaptation_pipeline import run_adaptation
from modules.learning_plan_generator.utils.plan_regeneration import stitch_regenerated_plan
from modules.content_generator import *
from modules.content_generator.agents.content_feedback_simulator import simulate_content_feedback_with_llm
from modules.content_generator.utils.mastery_evaluator import evaluate_mastery_submission
from modules.ai_chatbot_tutor import chat_with_tutor_with_llm
from modules.ai_chatbot_tutor.utils import safe_update_learning_preferences
from api_schemas import *
from config import load_config
from services import ContentPrefetchService
from utils import store
from utils import auth_store, auth_jwt
from utils.content_view import build_learning_content_view_model
from utils.motivational_messages import pick_motivational_message


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
from pydantic import BaseModel, ValidationError
from typing import Any, Dict, List, Optional, Tuple
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


_FSLSM_DIM_KEYS: Tuple[str, ...] = fslsm_adaptation.FSLSM_DIM_KEYS
_ADAPTATION_COOLDOWN_SECS = 300
_ADAPTATION_SNAPSHOT_TTL_SECS = 24 * 60 * 60
_ADAPTATION_DAILY_CAP = 0.20
_ADAPTATION_HYSTERESIS = 0.02
_adaptation_lock_guard = threading.Lock()
_adaptation_goal_locks: Dict[str, threading.Lock] = {}


def _get_adaptation_goal_lock(user_id: str, goal_id: int) -> threading.Lock:
    key = f"{user_id}:{goal_id}"
    with _adaptation_lock_guard:
        lock = _adaptation_goal_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _adaptation_goal_locks[key] = lock
    return lock


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_learning_content_payload(
    llm: Any,
    *,
    learner_profile: Any,
    learning_path: Any,
    learning_session: Any,
    use_search: bool,
    allow_parallel: bool,
    with_quiz: bool,
    goal_context: Any,
    method_name: str = "ami",
    cancel_event: Any = None,
) -> Dict[str, Any]:
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
        method_name=method_name,
        search_rag_manager=search_rag_manager,
        cancel_event=cancel_event,
    )
    learning_content["view_model"] = build_learning_content_view_model(
        learning_content.get("document", ""),
        learning_content.get("sources_used", []),
        content_format=learning_content.get("content_format", "standard"),
        audio_mode=learning_content.get("audio_mode"),
    )
    return learning_content


def _extract_fslsm_dims(profile: Dict[str, Any]) -> Dict[str, float]:
    return fslsm_adaptation.extract_fslsm_dims(profile)


def _default_adaptation_state() -> Dict[str, Any]:
    return fslsm_adaptation.default_adaptation_state()


def _normalize_adaptation_state(goal: Dict[str, Any]) -> Dict[str, Any]:
    return fslsm_adaptation.normalize_adaptation_state(goal)


def _path_version_hash(goal: Dict[str, Any]) -> str:
    return fslsm_adaptation.path_version_hash(goal)


def _current_path_hash(user_id: str, goal_id: int) -> str:
    return _path_version_hash(store.get_goal(user_id, goal_id) or {})


def _compute_band_state(
    dims: Dict[str, float],
    prev_band_state: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    return fslsm_adaptation.compute_band_state(
        dims,
        prev_band_state=prev_band_state,
        hysteresis=_ADAPTATION_HYSTERESIS,
    )


def _build_mastery_results_for_plan(learning_path: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return fslsm_adaptation.build_mastery_results_for_plan(
        learning_path,
        mastery_threshold_default=APP_CONFIG["mastery_threshold_default"],
    )


def _any_severe_mastery_failure(mastery_results: List[Dict[str, Any]]) -> bool:
    return fslsm_adaptation.any_severe_mastery_failure(
        mastery_results,
        mastery_threshold_default=APP_CONFIG["mastery_threshold_default"],
    )


def _build_adaptation_fingerprint(
    *,
    goal_id: int,
    band_state_by_dim: Dict[str, str],
    evidence_windows: Dict[str, Any],
    mode: str,
    path_version: str,
) -> str:
    return fslsm_adaptation.build_adaptation_fingerprint(
        goal_id=goal_id,
        band_state_by_dim=band_state_by_dim,
        evidence_windows=evidence_windows,
        mode=mode,
        path_version=path_version,
    )


def _session_signal_keys(
    session: Dict[str, Any],
    learning_content: Optional[Dict[str, Any]] = None,
) -> List[str]:
    return fslsm_adaptation.session_signal_keys(session, learning_content)


def _record_snapshot_timestamp(
    user_id: str,
    goal_id: int,
    goal: Optional[Dict[str, Any]] = None,
) -> None:
    goal_obj = goal or store.get_goal(user_id, goal_id)
    if not isinstance(goal_obj, dict):
        return
    state = _normalize_adaptation_state(goal_obj)
    state["snapshot_saved_at"] = _now_iso()
    store.patch_goal(user_id, goal_id, {"adaptation_state": state})


def _get_snapshot_with_ttl(
    user_id: str,
    goal_id: int,
    goal: Dict[str, Any],
    adaptation_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    snapshot = store.get_profile_snapshot(user_id, goal_id)
    if not isinstance(snapshot, dict):
        return None
    saved_at = adaptation_state.get("snapshot_saved_at")
    saved_ts = _parse_iso_ts(saved_at)
    if saved_ts is None:
        return snapshot
    if datetime.now(timezone.utc).timestamp() - saved_ts <= _ADAPTATION_SNAPSHOT_TTL_SECS:
        return snapshot
    store.delete_profile_snapshot(user_id, goal_id)
    adaptation_state["snapshot_saved_at"] = None
    store.patch_goal(user_id, goal_id, {"adaptation_state": adaptation_state})
    return None


def _append_evidence(
    evidence_windows: Dict[str, Any],
    key: str,
    *,
    severe_failure: bool,
    strong_success: bool,
) -> None:
    fslsm_adaptation.append_evidence(
        evidence_windows,
        key,
        severe_failure=severe_failure,
        strong_success=strong_success,
    )


def _update_fslsm_from_evidence(
    profile: Dict[str, Any],
    adaptation_state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    return fslsm_adaptation.update_fslsm_from_evidence(
        profile,
        adaptation_state,
        daily_cap=_ADAPTATION_DAILY_CAP,
    )


def _reset_adaptation_on_profile_sign_flip(
    user_id: str,
    goal_id: int,
    old_profile: Dict[str, Any],
    new_profile: Dict[str, Any],
) -> None:
    with _get_adaptation_goal_lock(user_id, goal_id):
        goal = store.get_goal(user_id, goal_id)
        if not isinstance(goal, dict):
            return
        adaptation_state = _normalize_adaptation_state(goal)
        flipped_dims = fslsm_adaptation.clear_opposite_evidence_on_sign_flip(
            old_profile if isinstance(old_profile, dict) else {},
            new_profile if isinstance(new_profile, dict) else {},
            adaptation_state,
        )
        if not flipped_dims:
            return
        adaptation_state["updated_at"] = _now_iso()
        store.patch_goal(user_id, goal_id, {"adaptation_state": adaptation_state})


def _build_adaptation_signal(
    goal: Dict[str, Any],
    profile: Dict[str, Any],
    adaptation_state: Dict[str, Any],
    snapshot_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str], List[str], Dict[str, str]]:
    return fslsm_adaptation.build_adaptation_signal(
        goal,
        profile,
        adaptation_state,
        mastery_threshold_default=APP_CONFIG["mastery_threshold_default"],
        snapshot_profile=snapshot_profile,
        hysteresis=_ADAPTATION_HYSTERESIS,
    )


def _build_goal_runtime_state(user_id: str, goal_id: int) -> dict:
    goal = _goal_or_404(user_id, goal_id)
    profile = store.get_profile(user_id, goal_id) or {}
    adaptation_state = _normalize_adaptation_state(goal)
    snapshot_profile = _get_snapshot_with_ttl(user_id, goal_id, goal, adaptation_state)
    sessions = []
    learning_path = goal.get("learning_path", [])
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
    adaptation_suggested, adaptation_message, sources, _current_band_state = _build_adaptation_signal(
        goal,
        profile,
        adaptation_state,
        snapshot_profile=snapshot_profile,
    )
    return {
        "goal_id": goal_id,
        "adaptation": {
            "suggested": adaptation_suggested,
            "message": adaptation_message,
            "sources": sources,
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

@app.post("/profile/auto-update")
async def auto_update_profile(request: AutoProfileUpdateRequest):
    """
    If profile doesn't exist: initialize it (needs learning_goal + learner_information + skill_gaps).
    If profile exists: update it using EVENT_STORE[user_id] as learner_interactions.
    """
    try:
        user_id = request.user_id
        goal_id = request.goal_id
        llm = get_llm(request.model_provider, request.model_name)
        interactions = store.get_events(user_id)

        # Normalize optional structured fields
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

        mode, profile = auto_update_learner_profile(
            llm=llm,
            user_id=user_id,
            goal_id=goal_id,
            interactions=interactions,
            learning_goal=request.learning_goal,
            learner_info=learner_info,
            skill_gaps=skill_gaps,
            session_information=request.session_information,
            get_profile_fn=store.get_profile,
            upsert_profile_fn=store.upsert_profile,
            initialize_fn=initialize_learner_profile_with_llm,
            update_fn=update_learner_profile_with_llm,
        )
        return {
            "ok": True,
            "mode": mode,
            "user_id": user_id,
            "goal_id": goal_id,
            "event_count_used": len(interactions),
            "learner_profile": profile,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
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
    goal_before = store.get_goal(user_id, goal_id)
    if goal_before is None:
        raise HTTPException(status_code=404, detail="Goal not found")
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
async def get_learning_content(user_id: str, goal_id: int, session_index: int, no_wait: bool = False):
    started = time.perf_counter()
    path_hash = PREFETCH_SERVICE.current_path_hash(user_id, goal_id)
    record = store.get_learning_content(user_id, goal_id, session_index)
    if record:
        PREFETCH_SERVICE.log_content_event(
            "get_content",
            user_id=user_id,
            goal_id=goal_id,
            session_index=session_index,
            trigger_source="api_get_learning_content",
            status="cache_hit",
            path_hash=path_hash,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
    if not record:
        if PREFETCH_SERVICE.prefetch_enabled() and not bool(no_wait):
            await asyncio.to_thread(
                PREFETCH_SERVICE.wait_for_inflight_content,
                user_id=user_id,
                goal_id=goal_id,
                session_index=session_index,
                timeout_secs=PREFETCH_SERVICE.prefetch_short_wait_secs(),
            )
            record = store.get_learning_content(user_id, goal_id, session_index)
            if record:
                PREFETCH_SERVICE.log_content_event(
                    "get_content",
                    user_id=user_id,
                    goal_id=goal_id,
                    session_index=session_index,
                    trigger_source="api_get_learning_content",
                    status="get_wait_hit",
                    path_hash=path_hash,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                )
    if not record:
        PREFETCH_SERVICE.log_content_event(
            "get_content",
            user_id=user_id,
            goal_id=goal_id,
            session_index=session_index,
            trigger_source="api_get_learning_content",
            status="get_miss",
            path_hash=path_hash,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )
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
            fslsm_dims = _extract_fslsm_dims(
                store.get_profile(request.user_id, request.goal_id) or {}
            )
            message = pick_motivational_message(
                kind, fslsm_dims, trigger_index=trigger_count // 2
            )
            activity["trigger_events"].append({"kind": kind, "time": event_time})
            trigger = {"show": True, "kind": kind, "message": message}
    else:
        _close_open_interval(activity, event_time, interval)

    if activity.get("intervals"):
        activity["start_time"] = activity["intervals"][0].get("start_time")
        activity["end_time"] = activity["intervals"][-1].get("end_time")
    store.upsert_session_activity(request.user_id, request.goal_id, request.session_index, activity)
    if request.event_type == "start":
        goal_for_prefetch = store.get_goal(request.user_id, request.goal_id) or {}
        next_idx = PREFETCH_SERVICE.first_unlearned_session_index(
            goal_for_prefetch.get("learning_path", []),
            start_after=request.session_index,
        )
        PREFETCH_SERVICE.log_content_event(
            "session_start_target",
            user_id=request.user_id,
            goal_id=request.goal_id,
            session_index=int(next_idx) if next_idx is not None else -1,
            trigger_source="session_start",
            status="resolved_next_session" if next_idx is not None else "no_candidate",
            path_hash=_path_version_hash(goal_for_prefetch),
            duration_ms=0.0,
            current_session_index=request.session_index,
        )
        if next_idx is not None:
            PREFETCH_SERVICE.enqueue_for_session(
                user_id=request.user_id,
                goal_id=request.goal_id,
                session_index=next_idx,
                trigger_source="session_start",
                apply_cooldown=True,
            )
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
    merged, profile_updated = safe_update_learning_preferences(
        llm,
        learner_interactions=feedback,
        learner_information="",
        user_id=request.user_id,
        goal_id=request.goal_id,
        get_profile_fn=store.get_profile,
        save_snapshot_fn=store.save_profile_snapshot,
        record_snapshot_timestamp_fn=_record_snapshot_timestamp,
        update_learning_preferences_fn=update_learning_preferences_with_llm,
        reset_adaptation_on_sign_flip_fn=_reset_adaptation_on_profile_sign_flip,
        upsert_profile_fn=store.upsert_profile,
        refresh_goal_profile_fn=_refresh_goal_profile,
    )
    return {
        "ok": True,
        "goal": _goal_aggregate_or_404(request.user_id, request.goal_id),
        "learner_profile": merged,
        "profile_updated": profile_updated,
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
    try:
        return compute_behavioral_metrics(
            user_id=user_id,
            goal_id=goal_id,
            idle_timeout_secs=APP_CONFIG["motivational_trigger_interval_secs"],
            get_all_goals_fn=store.get_all_goals_for_user,
            get_session_activity_fn=store.get_session_activity,
            get_mastery_history_fn=store.get_mastery_history,
            sum_activity_duration_fn=_sum_activity_duration_secs,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/evaluate-mastery")
async def evaluate_mastery(request: MasteryEvaluationRequest):
    """Evaluate quiz answers, compute score, and determine mastery status."""
    goal = _goal_or_404(request.user_id, request.goal_id)

    learning_path = goal.get("learning_path", [])
    if request.session_index < 0 or request.session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[request.session_index]
    cached = store.get_learning_content(request.user_id, request.goal_id, request.session_index) or {}
    quiz_data = (cached.get("learning_content") or {}).get("quizzes")
    if not quiz_data:
        raise HTTPException(status_code=404, detail="No quiz data found for this session")

    llm = get_llm()
    learning_content_payload = (cached.get("learning_content") if isinstance(cached, dict) else {}) or {}
    profile = store.get_profile(request.user_id, request.goal_id) or {}

    # Update session mastery score first so adaptation_state reflects updated path
    result = evaluate_mastery_submission(
        llm=llm,
        quiz_data=quiz_data,
        quiz_answers=request.quiz_answers,
        session=session,
        adaptation_state=_normalize_adaptation_state(goal),
        profile=profile,
        learning_content_payload=learning_content_payload,
        mastery_threshold_by_proficiency=APP_CONFIG["mastery_threshold_by_proficiency"],
        mastery_threshold_default=APP_CONFIG["mastery_threshold_default"],
        adaptation_daily_cap=_ADAPTATION_DAILY_CAP,
    )

    # Update session in goal store
    session["mastery_score"] = result["score_percentage"]
    session["is_mastered"] = result["is_mastered"]
    session["mastery_threshold"] = result["threshold"]
    learning_path[request.session_index] = session
    store.patch_goal(request.user_id, request.goal_id, {"learning_path": learning_path})

    # Persist FSLSM adjustments if any were made
    if any(abs(v) > 1e-9 for v in result["fslsm_adjustments"].values()):
        store.upsert_profile(request.user_id, request.goal_id, result["updated_profile"])
        profile = result["updated_profile"]

    store.patch_goal(request.user_id, request.goal_id, {"adaptation_state": result["updated_adaptation_state"]})
    store.append_mastery_history(request.user_id, request.goal_id, _compute_mastery_rate(profile))

    runtime_adaptation = _build_goal_runtime_state(request.user_id, request.goal_id).get("adaptation", {})
    response: Dict[str, Any] = {
        "score_percentage": result["score_percentage"],
        "is_mastered": result["is_mastered"],
        "threshold": result["threshold"],
        "correct_count": result["correct_count"],
        "total_count": result["total_count"],
        "session_id": session.get("id", ""),
        "plan_adaptation_suggested": bool(runtime_adaptation.get("suggested", False)),
        "fslsm_adjustments": result["fslsm_adjustments"],
    }
    if result["short_answer_feedback"]:
        response["short_answer_feedback"] = result["short_answer_feedback"]
    if result["open_ended_feedback"]:
        response["open_ended_feedback"] = result["open_ended_feedback"]
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


@app.post("/adapt-learning-path")
async def adapt_learning_path(request: AdaptLearningPathRequest):
    """Detect preference/mastery changes and adapt the learning path accordingly."""
    llm = get_llm(request.model_provider, request.model_name)
    ctx: Dict[str, Any] = {}

    try:
        with _get_adaptation_goal_lock(request.user_id, request.goal_id):
            goal = _goal_or_404(request.user_id, request.goal_id)
            adaptation_state = _normalize_adaptation_state(goal)
            profile_from_store = store.get_profile(request.user_id, request.goal_id) or {}

            mode = "auto"
            effective_profile = profile_from_store
            if isinstance(request.new_learner_profile, str) and request.new_learner_profile.strip():
                mode = "explicit"
                try:
                    parsed_profile = ast.literal_eval(request.new_learner_profile)
                except Exception:
                    parsed_profile = {}
                if isinstance(parsed_profile, dict) and parsed_profile:
                    effective_profile = parsed_profile
                    store.upsert_profile(request.user_id, request.goal_id, effective_profile)

            snapshot_profile = _get_snapshot_with_ttl(
                request.user_id, request.goal_id, goal, adaptation_state
            )

            current_plan_before = {"learning_path": goal.get("learning_path", [])}
            response = run_adaptation(
                llm=llm,
                goal_id=request.goal_id,
                goal=goal,
                effective_profile=effective_profile,
                adaptation_state=adaptation_state,
                snapshot_profile=snapshot_profile,
                mode=mode,
                force=request.force,
                cooldown_secs=_ADAPTATION_COOLDOWN_SECS,
                mastery_threshold_default=APP_CONFIG["mastery_threshold_default"],
                hysteresis=_ADAPTATION_HYSTERESIS,
                patch_goal_fn=store.patch_goal,
                delete_profile_snapshot_fn=store.delete_profile_snapshot,
                reschedule_fn=reschedule_learning_path_with_llm,
                schedule_agentic_fn=schedule_learning_path_agentic,
                stitch_fn=stitch_regenerated_plan,
                evaluate_plan_fn=evaluate_plan,
                ctx=ctx,
                user_id=request.user_id,
            )

            if response.get("adaptation", {}).get("status") == "applied":
                result_plan = {"learning_path": response.get("learning_path", [])}
                changed_future_indices = PREFETCH_SERVICE.changed_unlearned_indices(
                    current_plan_before.get("learning_path", []),
                    result_plan.get("learning_path", []),
                )
                PREFETCH_SERVICE.invalidate_learning_content_indices(
                    request.user_id, request.goal_id, changed_future_indices
                )
                PREFETCH_SERVICE.cancel_inflight_for_goal(request.user_id, request.goal_id)
                # Prefetch is only triggered when the learner starts a session.

            return response

    except HTTPException:
        raise
    except Exception as e:
        fingerprint = ctx.get("fingerprint")
        if fingerprint:
            try:
                goal = _goal_or_404(request.user_id, request.goal_id)
                state = _normalize_adaptation_state(goal)
                state["last_failed_fingerprint"] = fingerprint
                state["last_failed_at"] = _now_iso()
                state["last_result"] = "failed"
                state["last_reason"] = str(e)
                store.patch_goal(request.user_id, request.goal_id, {"adaptation_state": state})
            except Exception:
                pass
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


_prefetch_cfg = app_config.get("prefetch", {}) if hasattr(app_config, "get") else {}
APP_CONFIG = {
    "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
    "default_session_count": 8,
    "default_llm_type": "gpt4o",
    "default_method_name": "ami",
    "motivational_trigger_interval_secs": 180,
    "max_refinement_iterations": 5,
    "prefetch_enabled": bool(_prefetch_cfg.get("enabled", True)),
    "prefetch_wait_short_secs": int(_prefetch_cfg.get("wait_short_secs", 8)),
    "prefetch_wait_long_secs": int(_prefetch_cfg.get("wait_long_secs", 130)),
    "prefetch_cooldown_secs": int(_prefetch_cfg.get("cooldown_secs", 20)),
    "prefetch_max_workers": int(_prefetch_cfg.get("max_workers", 2)),
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
    "adaptation_hysteresis_margin": 0.02,
    "adaptation_retry_cooldown_secs": 300,
    "adaptation_snapshot_ttl_secs": 86400,
    "adaptation_daily_movement_cap": 0.20,
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

PREFETCH_SERVICE = ContentPrefetchService(
    app_config=APP_CONFIG,
    logger=logger,
    store=store,
    get_llm=get_llm,
    build_learning_content_payload=_build_learning_content_payload,
    path_hash_fn=_path_version_hash,
    current_path_hash_fn=_current_path_hash,
)


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

@app.post("/chat-with-tutor")
async def chat_with_autor(request: ChatWithAutorRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    try:
        if isinstance(request.messages, str) and request.messages.strip().startswith("["):
            converted_messages = ast.literal_eval(request.messages)
        else:
            return JSONResponse(status_code=400, content={"detail": "messages must be a JSON array string"})

        def _safe_tutor_preference_update(
            *,
            user_id: str,
            goal_id: int,
            latest_user_message: str,
            learner_information: str = "",
            signals: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            interactions = {
                "source": "ai_tutor_chat",
                "additional_comments": latest_user_message,
                "signals": signals or {},
            }
            updated_profile, profile_updated = safe_update_learning_preferences(
                llm,
                learner_interactions=interactions,
                learner_information=learner_information or "",
                user_id=user_id,
                goal_id=goal_id,
                max_fslsm_delta=0.05,
                get_profile_fn=store.get_profile,
                save_snapshot_fn=store.save_profile_snapshot,
                record_snapshot_timestamp_fn=_record_snapshot_timestamp,
                update_learning_preferences_fn=update_learning_preferences_with_llm,
                reset_adaptation_on_sign_flip_fn=_reset_adaptation_on_profile_sign_flip,
                upsert_profile_fn=store.upsert_profile,
                # Avoid cross-goal merge overwriting this turn's freshly-updated
                # preference signal before we return metadata to the caller.
                refresh_goal_profile_fn=lambda uid, gid: store.get_profile(uid, gid) or {},
            )
            return {
                "profile_updated": profile_updated,
                "updated_learner_profile": updated_profile if profile_updated else None,
                "reason": "Profile updated from strong tutor preference signal." if profile_updated else "No persisted preference change.",
            }

        result = chat_with_tutor_with_llm(
            llm,
            converted_messages,
            learner_profile,
            search_rag_manager=search_rag_manager,
            safe_preference_update_fn=_safe_tutor_preference_update,
            use_search=request.use_search if request.use_search is not None else True,
            top_k=request.top_k or 5,
            user_id=request.user_id,
            goal_id=request.goal_id,
            session_index=request.session_index,
            use_vector_retrieval=request.use_vector_retrieval,
            use_web_search=request.use_web_search,
            use_media_search=request.use_media_search,
            allow_preference_updates=(
                request.allow_preference_updates
                if request.allow_preference_updates is not None
                else True
            ),
            learner_information=request.learner_information or "",
            return_metadata=bool(request.return_metadata),
        )
        if isinstance(result, dict):
            response_payload = {
                "response": result.get("response", ""),
                "profile_updated": bool(result.get("profile_updated", False)),
            }
            updated_profile = result.get("updated_learner_profile")
            if isinstance(updated_profile, dict):
                response_payload["updated_learner_profile"] = updated_profile
            return response_payload
        return {"response": result}
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
    llm = LLMFactory.create(model="gpt-4o-mini", model_provider="openai", temperature=0)
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


@app.post("/audit-content-bias")
async def audit_content_bias(request: ContentBiasAuditRequest):
    llm = get_llm(request.model_provider, request.model_name)
    generated_content = request.generated_content
    learner_information = request.learner_information
    try:
        result = audit_content_bias_with_llm(llm, generated_content, learner_information)
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
        input_profile = learner_profile if isinstance(learner_profile, dict) else {}
        old_profile_for_reset = copy.deepcopy(input_profile)
        # Snapshot the pre-update FSLSM state so adapt-learning-path can compare old vs new.
        if request.user_id is not None and request.goal_id is not None:
            stored_profile = store.get_profile(request.user_id, request.goal_id)
            if isinstance(stored_profile, dict):
                input_profile = copy.deepcopy(stored_profile)
                old_profile_for_reset = copy.deepcopy(stored_profile)
            store.save_profile_snapshot(request.user_id, request.goal_id, old_profile_for_reset)
            _record_snapshot_timestamp(request.user_id, request.goal_id)
        slider_override_dims = extract_slider_override_dims(
            learner_interactions,
            fallback_dims=(
                input_profile.get("learning_preferences", {}).get("fslsm_dimensions", {})
                if isinstance(input_profile, dict)
                else {}
            ),
        )
        if slider_override_dims:
            learner_profile = copy.deepcopy(input_profile if isinstance(input_profile, dict) else {})
            prefs = learner_profile.setdefault("learning_preferences", {})
            if not isinstance(prefs, dict):
                prefs = {}
                learner_profile["learning_preferences"] = prefs
            prefs["fslsm_dimensions"] = slider_override_dims
        else:
            learner_profile = update_learning_preferences_with_llm(
                llm,
                input_profile,
                learner_interactions,
                learner_information,
            )
        if request.user_id is not None and request.goal_id is not None:
            _reset_adaptation_on_profile_sign_flip(
                request.user_id,
                request.goal_id,
                old_profile_for_reset,
                learner_profile if isinstance(learner_profile, dict) else {},
            )
            store.upsert_profile(request.user_id, request.goal_id, learner_profile)
        return {"learner_profile": learner_profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/update-learner-information")
async def update_learner_information(request: LearnerInformationUpdateRequest):
    llm = get_llm(request.model_provider, request.model_name)
    learner_profile = request.learner_profile
    edited_learner_information = request.edited_learner_information
    resume_text = request.resume_text
    try:
        if isinstance(learner_profile, str) and learner_profile.strip():
            try:
                learner_profile = ast.literal_eval(learner_profile)
            except Exception:
                learner_profile = {"raw": learner_profile}
        if isinstance(edited_learner_information, str):
            edited_learner_information = edited_learner_information.strip()
        if isinstance(resume_text, str):
            resume_text = resume_text.strip()

        input_profile = learner_profile if isinstance(learner_profile, dict) else {}
        old_profile_for_reset = copy.deepcopy(input_profile)

        if request.user_id is not None and request.goal_id is not None:
            stored_profile = store.get_profile(request.user_id, request.goal_id)
            if isinstance(stored_profile, dict):
                input_profile = copy.deepcopy(stored_profile)
                old_profile_for_reset = copy.deepcopy(stored_profile)
            store.save_profile_snapshot(request.user_id, request.goal_id, old_profile_for_reset)
            _record_snapshot_timestamp(request.user_id, request.goal_id)

        updated_profile = update_learner_information_with_llm(
            llm,
            input_profile,
            edited_learner_information=edited_learner_information or "",
            resume_text=resume_text or "",
        )
        if not isinstance(updated_profile, dict):
            updated_profile = copy.deepcopy(input_profile if isinstance(input_profile, dict) else {})

        if request.user_id is not None and request.goal_id is not None:
            _reset_adaptation_on_profile_sign_flip(
                request.user_id,
                request.goal_id,
                old_profile_for_reset,
                updated_profile if isinstance(updated_profile, dict) else {},
            )
            store.upsert_profile(request.user_id, request.goal_id, updated_profile)
            store.propagate_learner_information_to_all_goals(
                request.user_id,
                updated_profile.get("learner_information", ""),
            )
            persisted = store.get_profile(request.user_id, request.goal_id) or updated_profile
            return {"learner_profile": persisted}

        return {"learner_profile": updated_profile}
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
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
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
    except (ValidationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-learning-content")
async def generate_learning_content(request: LearningContentGenerationRequest):
    if request.method_name != "ami":
        raise HTTPException(status_code=400, detail="Unsupported method_name. Expected 'ami'.")

    llm = get_llm(request.model_provider, request.model_name)
    learning_path = _parse_jsonish(request.learning_path, request.learning_path)
    learner_profile = _parse_jsonish(request.learner_profile, request.learner_profile)
    learning_session = _parse_jsonish(request.learning_session, request.learning_session)
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    goal_context = request.goal_context
    cache_key: Optional[str] = None
    owner_token: Optional[str] = None
    path_hash_at_start: Optional[str] = None
    session_guard_hash_at_start: Optional[str] = None
    owner_terminal_status = "succeeded"
    started = time.perf_counter()

    try:
        has_cache_identity = (
            request.user_id is not None
            and request.goal_id is not None
            and request.session_index is not None
        )
        if has_cache_identity:
            cache_key = PREFETCH_SERVICE.content_cache_key(request.user_id, request.goal_id, request.session_index)
            path_hash_now = PREFETCH_SERVICE.current_path_hash(request.user_id, request.goal_id)
            session_guard_hash_at_start = PREFETCH_SERVICE.session_guard_hash_for_target(
                request.user_id,
                request.goal_id,
                request.session_index,
            )
            cached = store.get_learning_content(request.user_id, request.goal_id, request.session_index)
            if isinstance(cached, dict) and isinstance(cached.get("learning_content"), dict):
                PREFETCH_SERVICE.log_content_event(
                    "generate_content",
                    user_id=request.user_id,
                    goal_id=request.goal_id,
                    session_index=request.session_index,
                    trigger_source="on_demand",
                    status="cache_hit",
                    path_hash=path_hash_now,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                )
                return cached["learning_content"]
            if PREFETCH_SERVICE.prefetch_enabled():
                if PREFETCH_SERVICE.singleflight_status(cache_key) == "running":
                    PREFETCH_SERVICE.log_content_event(
                        "generate_content",
                        user_id=request.user_id,
                        goal_id=request.goal_id,
                        session_index=request.session_index,
                        trigger_source="on_demand",
                        status="join_wait",
                        path_hash=path_hash_now,
                        duration_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    await asyncio.to_thread(
                        PREFETCH_SERVICE.wait_for_inflight_terminal,
                        user_id=request.user_id,
                        goal_id=request.goal_id,
                        session_index=request.session_index,
                    )
                    cached = store.get_learning_content(request.user_id, request.goal_id, request.session_index)
                    if isinstance(cached, dict) and isinstance(cached.get("learning_content"), dict):
                        PREFETCH_SERVICE.log_content_event(
                            "generate_content",
                            user_id=request.user_id,
                            goal_id=request.goal_id,
                            session_index=request.session_index,
                            trigger_source="on_demand",
                            status="join_hit",
                            path_hash=path_hash_now,
                            duration_ms=(time.perf_counter() - started) * 1000.0,
                        )
                        return cached["learning_content"]

                while owner_token is None:
                    path_hash_now = PREFETCH_SERVICE.current_path_hash(request.user_id, request.goal_id)
                    path_hash_at_start = path_hash_now
                    session_guard_hash_at_start = PREFETCH_SERVICE.session_guard_hash_for_target(
                        request.user_id,
                        request.goal_id,
                        request.session_index,
                    )
                    owner_token = PREFETCH_SERVICE.singleflight_try_start(
                        cache_key,
                        path_hash_at_start=path_hash_at_start,
                        trigger_source="on_demand",
                        session_guard_hash_at_start=session_guard_hash_at_start,
                    )
                    if owner_token is not None:
                        break
                    PREFETCH_SERVICE.log_content_event(
                        "generate_content",
                        user_id=request.user_id,
                        goal_id=request.goal_id,
                        session_index=request.session_index,
                        trigger_source="on_demand",
                        status="join_wait",
                        path_hash=path_hash_now,
                        duration_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    await asyncio.to_thread(
                        PREFETCH_SERVICE.wait_for_inflight_terminal,
                        user_id=request.user_id,
                        goal_id=request.goal_id,
                        session_index=request.session_index,
                    )
                    cached = store.get_learning_content(request.user_id, request.goal_id, request.session_index)
                    if isinstance(cached, dict) and isinstance(cached.get("learning_content"), dict):
                        PREFETCH_SERVICE.log_content_event(
                            "generate_content",
                            user_id=request.user_id,
                            goal_id=request.goal_id,
                            session_index=request.session_index,
                            trigger_source="on_demand",
                            status="join_hit",
                            path_hash=path_hash_now,
                            duration_ms=(time.perf_counter() - started) * 1000.0,
                        )
                        return cached["learning_content"]
        if has_cache_identity:
            PREFETCH_SERVICE.log_content_event(
                "generate_content",
                user_id=request.user_id,
                goal_id=request.goal_id,
                session_index=request.session_index,
                trigger_source="on_demand",
                status="fallback_generate",
                path_hash=path_hash_at_start or PREFETCH_SERVICE.current_path_hash(request.user_id, request.goal_id),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        learning_content = _build_learning_content_payload(
            llm,
            learner_profile=learner_profile,
            learning_path=learning_path,
            learning_session=learning_session,
            use_search=use_search,
            allow_parallel=allow_parallel,
            with_quiz=with_quiz,
            goal_context=goal_context,
            method_name=request.method_name,
        )
        if has_cache_identity:
            stale, stale_reason, path_hash_current = PREFETCH_SERVICE.is_stale_for_target_session(
                user_id=request.user_id,
                goal_id=request.goal_id,
                session_index=request.session_index,
                session_guard_hash_at_start=session_guard_hash_at_start,
            )
            if stale:
                owner_terminal_status = "discarded"
                PREFETCH_SERVICE.log_content_event(
                    "generate_content",
                    user_id=request.user_id,
                    goal_id=request.goal_id,
                    session_index=request.session_index,
                    trigger_source="on_demand",
                    status="fallback_discarded",
                    path_hash=path_hash_at_start or path_hash_current,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    stale_reason=stale_reason,
                    path_hash_current=path_hash_current,
                )
            else:
                store.upsert_learning_content(
                    request.user_id,
                    request.goal_id,
                    request.session_index,
                    learning_content,
                )
                PREFETCH_SERVICE.log_content_event(
                    "generate_content",
                    user_id=request.user_id,
                    goal_id=request.goal_id,
                    session_index=request.session_index,
                    trigger_source="on_demand",
                    status="fallback_saved",
                    path_hash=path_hash_at_start or path_hash_current,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    path_hash_current=path_hash_current,
                )
        return learning_content
    except HTTPException as e:
        if owner_token and cache_key:
            owner_terminal_status = "failed"
            PREFETCH_SERVICE.singleflight_finish(
                cache_key,
                owner_token=owner_token,
                status="failed",
                error=str(e),
            )
            if request.user_id is not None and request.goal_id is not None and request.session_index is not None:
                PREFETCH_SERVICE.log_content_event(
                    "generate_content",
                    user_id=request.user_id,
                    goal_id=request.goal_id,
                    session_index=request.session_index,
                    trigger_source="on_demand",
                    status="failed",
                    path_hash=path_hash_at_start or PREFETCH_SERVICE.current_path_hash(request.user_id, request.goal_id),
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    error=str(e),
                )
        raise
    except Exception as e:
        if owner_token and cache_key:
            owner_terminal_status = "failed"
            PREFETCH_SERVICE.singleflight_finish(
                cache_key,
                owner_token=owner_token,
                status="failed",
                error=str(e),
            )
            if request.user_id is not None and request.goal_id is not None and request.session_index is not None:
                PREFETCH_SERVICE.log_content_event(
                    "generate_content",
                    user_id=request.user_id,
                    goal_id=request.goal_id,
                    session_index=request.session_index,
                    trigger_source="on_demand",
                    status="failed",
                    path_hash=path_hash_at_start or PREFETCH_SERVICE.current_path_hash(request.user_id, request.goal_id),
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    error=str(e),
                )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if owner_token and cache_key:
            PREFETCH_SERVICE.singleflight_finish(
                cache_key,
                owner_token=owner_token,
                status=owner_terminal_status,
            )

if __name__ == "__main__":
    server_cfg = app_config.get("server", {})
    host = app_config.get("server", {}).get("host", "127.0.0.1")
    port = int(app_config.get("server", {}).get("port", 8000))
    log_level = str(app_config.get("log_level", "debug")).lower()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
