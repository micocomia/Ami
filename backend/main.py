import os
import logging
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
import time
import uvicorn
import hydra
from omegaconf import DictConfig, OmegaConf
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from io import BytesIO
import pdfplumber
from base.llm_factory import LLMFactory
from base.searcher_factory import SearchRunner
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
import os
os.makedirs("data/audio", exist_ok=True)
app.mount("/static/audio", StaticFiles(directory="data/audio"), name="audio")
os.makedirs("data/diagrams", exist_ok=True)
app.mount("/static/diagrams", StaticFiles(directory="data/diagrams"), name="diagrams")
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from datetime import datetime


@app.on_event("startup")
def _load_stores():
    store.load()
    auth_store.load()
    if search_rag_manager.verified_content_manager:
        search_rag_manager.verified_content_manager.sync_verified_content(
            app_config.get("verified_content", {}).get("base_dir", "resources/verified-course-content")
        )

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


@app.get("/user-state/{user_id}")
async def get_user_state(user_id: str):
    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")
    return {"state": state}


@app.put("/user-state/{user_id}")
async def put_user_state(user_id: str, body: UserStateRequest):
    store.put_user_state(user_id, body.state)
    return {"ok": True}


@app.delete("/user-state/{user_id}")
async def delete_user_state(user_id: str):
    store.delete_user_state(user_id)
    return {"ok": True}


@app.delete("/user-data/{user_id}")
async def delete_user_data(user_id: str):
    """Delete all non-auth data for a user (profiles, events, state, snapshots).
    Used by Restart Onboarding so mastered skills and persona info are fully cleared."""
    store.delete_all_user_data(user_id)
    return {"ok": True}


@app.get("/behavioral-metrics/{user_id}")
async def get_behavioral_metrics(user_id: str, goal_id: Optional[int] = None):
    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")

    session_times = state.get("session_learning_times", {})
    mastery_history = state.get("learned_skills_history", {})
    goals = state.get("goals", [])

    # Filter sessions for the requested goal (keys are "{goal_id}-{session_id}")
    prefix = f"{goal_id}-" if goal_id is not None else None
    completed = []
    total_triggers = 0
    for key, times in session_times.items():
        if not isinstance(times, dict):
            continue
        if prefix and not str(key).startswith(prefix):
            continue
        start = times.get("start_time")
        end = times.get("end_time")
        if start is not None and end is not None:
            completed.append(max(end - start, 0.0))
        triggers = times.get("trigger_time_list", [])
        if len(triggers) > 1:
            total_triggers += len(triggers) - 1

    # Session completion from learning_path
    total_in_path = 0
    sessions_learned = 0
    if goal_id is not None:
        for g in goals:
            if isinstance(g, dict) and g.get("id") == goal_id:
                path = g.get("learning_path", [])
                total_in_path = len(path)
                sessions_learned = sum(1 for s in path if isinstance(s, dict) and s.get("if_learned"))
                break

    # Mastery history (keys may be int or str depending on serialization)
    history = []
    if isinstance(mastery_history, dict) and goal_id is not None:
        history = mastery_history.get(str(goal_id), mastery_history.get(goal_id, []))
    if not isinstance(history, list):
        history = []

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
        "mastery_history": history,
        "latest_mastery_rate": history[-1] if history else None,
    }


@app.post("/evaluate-mastery")
async def evaluate_mastery(request: MasteryEvaluationRequest):
    """Evaluate quiz answers, compute score, and determine mastery status."""
    from utils.quiz_scorer import compute_quiz_score, get_mastery_threshold_for_session
    from utils.solo_evaluator import evaluate_free_text_response, evaluate_short_answer_response

    state = store.get_user_state(request.user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")

    goals = state.get("goals", [])
    goal = None
    for g in goals:
        if isinstance(g, dict) and g.get("id") == request.goal_id:
            goal = g
            break
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    learning_path = goal.get("learning_path", [])
    if request.session_index < 0 or request.session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[request.session_index]

    # Retrieve cached quiz data
    session_uid = f"{request.goal_id}-{request.session_index}"
    doc_caches = state.get("document_caches", {})
    cached = doc_caches.get(session_uid, {})
    quiz_data = cached.get("quizzes")
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

    # Update session in state
    session["mastery_score"] = round(score_pct, 1)
    session["is_mastered"] = is_mastered
    session["mastery_threshold"] = threshold
    store.put_user_state(request.user_id, state)

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

    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")

    goals = state.get("goals", [])
    goal = None
    for g in goals:
        if isinstance(g, dict) and g.get("id") == goal_id:
            goal = g
            break
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    learning_path = goal.get("learning_path", [])
    if session_index < 0 or session_index >= len(learning_path):
        raise HTTPException(status_code=400, detail="Invalid session_index")

    session = learning_path[session_index]
    mix = get_quiz_mix_for_session(session, APP_CONFIG["quiz_mix_by_proficiency"])
    return mix


@app.get("/session-mastery-status/{user_id}")
async def session_mastery_status(user_id: str, goal_id: int):
    """Return mastery status for all sessions in a goal."""
    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")

    goals = state.get("goals", [])
    goal = None
    for g in goals:
        if isinstance(g, dict) and g.get("id") == goal_id:
            goal = g
            break
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

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

        # Load current state and previous profile
        state = store.get_user_state(request.user_id)
        if state is None:
            raise HTTPException(status_code=404, detail="No state found for this user_id")

        goals = state.get("goals", [])
        goal = None
        for g in goals:
            if isinstance(g, dict) and g.get("id") == request.goal_id:
                goal = g
                break
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")

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
    "default_method_name": "genmentor",
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


@app.post("/explore-knowledge-points")
async def explore_knowledge_points(request: KnowledgePointExplorationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    if isinstance(learner_profile, str) and learner_profile.strip():
        learner_profile = ast.literal_eval(learner_profile)
    if isinstance(learning_path, str) and learning_path.strip():
        learning_path = ast.literal_eval(learning_path)
    if isinstance(learning_session, str) and learning_session.strip():
        learning_session = ast.literal_eval(learning_session)
    try:
        knowledge_points = explore_knowledge_points_with_llm(llm, learner_profile, learning_path, learning_session)
        return knowledge_points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-point")
async def draft_knowledge_point(request: KnowledgePointDraftingRequest):
    from modules.content_generator.agents.learning_content_creator import (
        _get_fslsm_dim, _get_fslsm_input, _processing_perception_hints, _visual_formatting_hints,
    )
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_point = request.knowledge_point
    use_search = request.use_search
    fslsm_input = _get_fslsm_input(learner_profile)
    fslsm_processing = _get_fslsm_dim(learner_profile, "fslsm_processing")
    fslsm_perception = _get_fslsm_dim(learner_profile, "fslsm_perception")
    visual_hints = _visual_formatting_hints(fslsm_input)
    proc_perc_hints = _processing_perception_hints(fslsm_processing, fslsm_perception)
    try:
        knowledge_draft = draft_knowledge_point_with_llm(
            llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_point,
            use_search,
            visual_formatting_hints=visual_hints,
            processing_perception_hints=proc_perc_hints,
            search_rag_manager=search_rag_manager,
        )
        return {"knowledge_draft": knowledge_draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/draft-knowledge-points")
async def draft_knowledge_points(request: KnowledgePointsDraftingRequest):
    from modules.content_generator.agents.learning_content_creator import (
        _get_fslsm_dim, _get_fslsm_input, _processing_perception_hints, _visual_formatting_hints,
    )
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    fslsm_input = _get_fslsm_input(learner_profile)
    fslsm_processing = _get_fslsm_dim(learner_profile, "fslsm_processing")
    fslsm_perception = _get_fslsm_dim(learner_profile, "fslsm_perception")
    visual_hints = _visual_formatting_hints(fslsm_input)
    proc_perc_hints = _processing_perception_hints(fslsm_processing, fslsm_perception)
    try:
        knowledge_drafts = draft_knowledge_points_with_llm(
            llm, learner_profile, learning_path, learning_session, knowledge_points,
            allow_parallel, use_search,
            visual_formatting_hints=visual_hints,
            processing_perception_hints=proc_perc_hints,
            search_rag_manager=search_rag_manager,
        )
        return {"knowledge_drafts": knowledge_drafts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/integrate-learning-document")
async def integrate_learning_document(request: LearningDocumentIntegrationRequest):
    from modules.content_generator.agents.learning_content_creator import (
        _get_fslsm_dim, _get_fslsm_input, _understanding_hints,
        _FSLSM_STRONG, _FSLSM_MODERATE, _narrative_allowance,
    )
    from modules.content_generator.agents.learning_document_integrator import build_inline_assets_plan
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_path = request.learning_path
    learning_session = request.learning_session
    knowledge_points = request.knowledge_points
    knowledge_drafts = request.knowledge_drafts
    output_markdown = request.output_markdown
    fslsm_understanding = _get_fslsm_dim(learner_profile, "fslsm_understanding")
    fslsm_input = _get_fslsm_input(learner_profile)
    und_hints = _understanding_hints(fslsm_understanding)

    # Audio-visual pipeline requires a rendered markdown string to operate on.
    # When any adaptation applies, force output_markdown=True so the integrator
    # returns a string rather than a raw document_structure dict.
    needs_av = fslsm_input <= -_FSLSM_MODERATE or fslsm_input >= _FSLSM_MODERATE
    effective_output_markdown = True if needs_av else output_markdown

    # Normalise knowledge_points: the request field may arrive as a JSON string
    if isinstance(knowledge_points, str):
        try:
            knowledge_points = ast.literal_eval(knowledge_points)
        except Exception:
            knowledge_points = []
    if not isinstance(knowledge_points, list):
        knowledge_points = []
    if isinstance(knowledge_drafts, str):
        try:
            knowledge_drafts = ast.literal_eval(knowledge_drafts)
        except Exception:
            knowledge_drafts = []
    if not isinstance(knowledge_drafts, list):
        knowledge_drafts = []

    # Find media resources for visual and verbal learners before integration
    media_resources = []
    narrative_resources = []
    inline_assets_plan = None
    inline_assets_stats = {"placed_assets": 0}
    session_title = learning_session.get("title", "") if isinstance(learning_session, dict) else ""
    max_videos, max_images, max_audio = 0, 0, 0
    if fslsm_input <= -_FSLSM_MODERATE:
        max_videos = 2 if fslsm_input <= -_FSLSM_STRONG else 1
        max_images = 2 if fslsm_input <= -_FSLSM_STRONG else 0
    elif fslsm_input >= _FSLSM_MODERATE:
        max_audio = 2 if fslsm_input >= _FSLSM_STRONG else 1

    if max_videos or max_images or max_audio:
        from modules.content_generator.agents.media_resource_finder import find_media_resources
        from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm
        _search_runner = getattr(search_rag_manager, "search_runner", None)
        if _search_runner is None:
            try:
                from config.loader import default_config
                from base.searcher_factory import SearchRunner
                _search_runner = SearchRunner.from_config(default_config)
            except Exception:
                pass
        try:
            media_resources = find_media_resources(
                _search_runner,
                knowledge_points,
                max_videos=max_videos,
                max_images=max_images,
                max_audio=max_audio,
                session_context=session_title,
            )
        except Exception:
            media_resources = []
        if media_resources:
            kp_names = [kp.get("name", "") if isinstance(kp, dict) else str(kp) for kp in knowledge_points]
            media_resources = filter_media_resources_with_llm(
                llm, media_resources, session_title=session_title, knowledge_point_names=kp_names
            )

    # Generate verbal narrative equivalents (short stories/poems), then plan inline placement.
    narrative_allowance = _narrative_allowance(fslsm_input)
    if narrative_allowance > 0:
        try:
            from modules.content_generator.agents.narrative_resource_generator import (
                generate_narrative_resources_with_llm,
            )
            narrative_resources = generate_narrative_resources_with_llm(
                llm,
                knowledge_points,
                knowledge_drafts,
                session_title=session_title,
                max_narratives=narrative_allowance,
                include_tts=True,
            )
        except Exception:
            narrative_resources = []

    if media_resources or narrative_resources:
        inline_assets_plan, inline_assets_stats = build_inline_assets_plan(
            knowledge_points=knowledge_points,
            knowledge_drafts=knowledge_drafts,
            media_resources=media_resources,
            narrative_resources=narrative_resources,
            max_assets_per_subsection=2,
        )

    try:
        learning_document = integrate_learning_document_with_llm(
            llm, learner_profile, learning_path, learning_session, knowledge_points, knowledge_drafts,
            effective_output_markdown,
            understanding_hints=und_hints,
            media_resources=media_resources if media_resources else None,
            narrative_resources=narrative_resources if narrative_resources else None,
            inline_assets_plan=inline_assets_plan,
        )

        # Determine content format and optional host-expert listen mode.
        content_format = "standard"
        audio_url = None
        audio_mode = None

        if fslsm_input <= -_FSLSM_MODERATE:
            content_format = "visual_enhanced"

        if fslsm_input >= _FSLSM_MODERATE:
            content_format = "audio_enhanced"
            audio_mode = "host_expert_optional"
            from modules.content_generator.agents.podcast_style_converter import convert_to_podcast_with_llm
            from modules.content_generator.agents.tts_generator import generate_tts_audio
            try:
                host_expert_script = convert_to_podcast_with_llm(
                    llm, learning_document, learner_profile, mode="full"
                )
                audio_url = generate_tts_audio(host_expert_script)
            except Exception:
                audio_url = None

        return {
            "learning_document": learning_document,
            "content_format": content_format,
            "audio_url": audio_url,
            "audio_mode": audio_mode,
            "inline_assets_count": int((inline_assets_stats or {}).get("placed_assets", 0)),
            "inline_assets_placement_stats": inline_assets_stats or {},
            # Tells the frontend whether learning_document is already a rendered
            # markdown string (True) or still a raw document_structure dict (False).
            "document_is_markdown": needs_av,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-document-quizzes")
async def generate_document_quizzes(request: KnowledgeQuizGenerationRequest):
    llm = get_llm()
    learner_profile = request.learner_profile
    learning_document = request.learning_document
    single_choice_count = request.single_choice_count
    multiple_choice_count = request.multiple_choice_count
    true_false_count = request.true_false_count
    short_answer_count = request.short_answer_count
    open_ended_count = request.open_ended_count
    try:
        document_quiz = generate_document_quizzes_with_llm(llm, learner_profile, learning_document, single_choice_count, multiple_choice_count, true_false_count, short_answer_count, open_ended_count)
        return {"document_quiz": document_quiz}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tailor-knowledge-content")
async def tailor_knowledge_content(request: TailoredContentGenerationRequest):
    llm = get_llm()
    learning_path = request.learning_path
    learner_profile = request.learner_profile
    learning_session = request.learning_session
    use_search = request.use_search
    allow_parallel = request.allow_parallel
    with_quiz = request.with_quiz
    try:
        tailored_content = create_learning_content_with_llm(
            llm, learner_profile, learning_path, learning_session,
            allow_parallel=allow_parallel, with_quiz=with_quiz, use_search=use_search,
            quiz_mix_config=APP_CONFIG["quiz_mix_by_proficiency"],
        )
        return {"tailored_content": tailored_content}
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
