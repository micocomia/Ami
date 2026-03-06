"""JSON file-backed persistence for learner profiles, goals, content, and activity."""

import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.learner_profiler.schemas import refresh_learning_preferences_derived_fields

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"
_PROFILES_PATH = _DATA_DIR / "profiles.json"
_EVENTS_PATH = _DATA_DIR / "events.json"
_PROFILE_SNAPSHOTS_PATH = _DATA_DIR / "profile_snapshots.json"
_GOALS_PATH = _DATA_DIR / "goals.json"
_LEARNING_CONTENT_PATH = _DATA_DIR / "learning_content.json"
_SESSION_ACTIVITY_PATH = _DATA_DIR / "session_activity.json"
_MASTERY_HISTORY_PATH = _DATA_DIR / "mastery_history.json"

_lock = threading.Lock()

# keyed by "{user_id}:{goal_id}"
_profiles: Dict[str, Dict[str, Any]] = {}
# keyed by user_id
_events: Dict[str, List[Dict[str, Any]]] = {}
# keyed by "{user_id}:{goal_id}" — pre-update snapshots for adapt comparison
_profile_snapshots: Dict[str, Dict[str, Any]] = {}
# keyed by "{user_id}:{goal_id}"
_goals: Dict[str, Dict[str, Any]] = {}
# keyed by "{user_id}:{goal_id}:{session_index}"
_learning_content_cache: Dict[str, Dict[str, Any]] = {}
# keyed by "{user_id}:{goal_id}:{session_index}"
_session_activity: Dict[str, Dict[str, Any]] = {}
# keyed by "{user_id}:{goal_id}"
_mastery_history: Dict[str, List[Dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load():
    """Read persisted data from disk into memory. Call once at startup."""
    global _profiles, _events, _profile_snapshots, _goals, _learning_content_cache, _session_activity, _mastery_history
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, target_name in (
        (_PROFILES_PATH, "_profiles"),
        (_EVENTS_PATH, "_events"),
        (_PROFILE_SNAPSHOTS_PATH, "_profile_snapshots"),
        (_GOALS_PATH, "_goals"),
        (_LEARNING_CONTENT_PATH, "_learning_content_cache"),
        (_SESSION_ACTIVITY_PATH, "_session_activity"),
        (_MASTERY_HISTORY_PATH, "_mastery_history"),
    ):
        target = {}
        if path.exists():
            try:
                target = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                target = {}
        globals()[target_name] = target


def _flush_json(path: Path, payload: Dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _profile_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def _goal_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def _content_key(user_id: str, goal_id: int, session_index: int) -> str:
    return f"{user_id}:{goal_id}:{session_index}"


def _mastery_history_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


# ---------------- profiles ----------------

def upsert_profile(user_id: str, goal_id: int, profile: Dict[str, Any]):
    refresh_learning_preferences_derived_fields(profile)
    with _lock:
        _profiles[_profile_key(user_id, goal_id)] = copy.deepcopy(profile)
        _flush_json(_PROFILES_PATH, _profiles)


def get_profile(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    profile = _profiles.get(_profile_key(user_id, goal_id))
    return copy.deepcopy(profile) if isinstance(profile, dict) else None


def get_all_profiles_for_user(user_id: str) -> Dict[int, Dict[str, Any]]:
    prefix = f"{user_id}:"
    result = {}
    for key, profile in _profiles.items():
        if key.startswith(prefix):
            gid = key[len(prefix):]
            try:
                result[int(gid)] = copy.deepcopy(profile)
            except ValueError:
                result[gid] = copy.deepcopy(profile)
    return result


def save_profile_snapshot(user_id: str, goal_id: int, profile: Dict[str, Any]):
    with _lock:
        _profile_snapshots[_profile_key(user_id, goal_id)] = profile
        _flush_json(_PROFILE_SNAPSHOTS_PATH, _profile_snapshots)


def get_profile_snapshot(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return _profile_snapshots.get(_profile_key(user_id, goal_id))


def delete_profile_snapshot(user_id: str, goal_id: int):
    with _lock:
        _profile_snapshots.pop(_profile_key(user_id, goal_id), None)
        _flush_json(_PROFILE_SNAPSHOTS_PATH, _profile_snapshots)


# ---------------- events ----------------

def append_event(user_id: str, event: Dict[str, Any]):
    with _lock:
        _events.setdefault(user_id, []).append(event)
        _events[user_id] = _events[user_id][-200:]
        _flush_json(_EVENTS_PATH, _events)


def get_events(user_id: str) -> List[Dict[str, Any]]:
    return _events.get(user_id, [])


# ---------------- goals ----------------

def _next_goal_id_for_user(user_id: str) -> int:
    goal_ids = [g.get("id") for g in get_all_goals_for_user(user_id, include_deleted=True) if isinstance(g.get("id"), int)]
    return (max(goal_ids) + 1) if goal_ids else 0


def create_goal(user_id: str, goal_payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    goal_id = _next_goal_id_for_user(user_id)
    goal = {
        "id": goal_id,
        "user_id": user_id,
        "learning_goal": goal_payload.get("learning_goal", ""),
        "skill_gaps": goal_payload.get("skill_gaps", []),
        "goal_assessment": goal_payload.get("goal_assessment"),
        "goal_context": goal_payload.get("goal_context", {}),
        "retrieved_sources": goal_payload.get("retrieved_sources", []),
        "bias_audit": goal_payload.get("bias_audit"),
        "profile_fairness": goal_payload.get("profile_fairness"),
        "learning_path": goal_payload.get("learning_path", []),
        "is_completed": bool(goal_payload.get("is_completed", False)),
        "is_deleted": bool(goal_payload.get("is_deleted", False)),
        "created_at": now,
        "updated_at": now,
    }
    with _lock:
        _goals[_goal_key(user_id, goal_id)] = goal
        _flush_json(_GOALS_PATH, _goals)
    return goal


def get_goal(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    goal = _goals.get(_goal_key(user_id, goal_id))
    return copy.deepcopy(goal) if isinstance(goal, dict) else None


def get_all_goals_for_user(user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
    prefix = f"{user_id}:"
    goals = []
    for key, goal in _goals.items():
        if key.startswith(prefix) and isinstance(goal, dict):
            if include_deleted or not goal.get("is_deleted", False):
                goals.append(copy.deepcopy(goal))
    goals.sort(key=lambda item: item.get("id", 0))
    return goals


def patch_goal(user_id: str, goal_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = _goal_key(user_id, goal_id)
    with _lock:
        existing = _goals.get(key)
        if not isinstance(existing, dict):
            return None
        existing.update({k: v for k, v in updates.items() if k not in {"id", "user_id", "created_at"}})
        existing["updated_at"] = _now_iso()
        _goals[key] = existing
        _flush_json(_GOALS_PATH, _goals)
        return copy.deepcopy(existing)


def delete_goal(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return patch_goal(user_id, goal_id, {"is_deleted": True})


def list_goal_aggregates(user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
    return [assemble_goal_aggregate(user_id, goal) for goal in get_all_goals_for_user(user_id, include_deleted=include_deleted)]


def get_goal_aggregate(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    goal = get_goal(user_id, goal_id)
    if not goal:
        return None
    return assemble_goal_aggregate(user_id, goal)


def assemble_goal_aggregate(user_id: str, goal: Dict[str, Any]) -> Dict[str, Any]:
    aggregate = copy.deepcopy(goal)
    aggregate["learner_profile"] = get_profile(user_id, int(goal.get("id", 0))) or {}
    return aggregate


# ---------------- learning content cache ----------------

def upsert_learning_content(user_id: str, goal_id: int, session_index: int, learning_content: Dict[str, Any]) -> Dict[str, Any]:
    key = _content_key(user_id, goal_id, session_index)
    now = _now_iso()
    with _lock:
        existing = _learning_content_cache.get(key, {})
        record = {
            "user_id": user_id,
            "goal_id": goal_id,
            "session_index": session_index,
            "learning_content": learning_content,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        _learning_content_cache[key] = record
        _flush_json(_LEARNING_CONTENT_PATH, _learning_content_cache)
        return copy.deepcopy(record)


def get_learning_content(user_id: str, goal_id: int, session_index: int) -> Optional[Dict[str, Any]]:
    record = _learning_content_cache.get(_content_key(user_id, goal_id, session_index))
    return copy.deepcopy(record) if isinstance(record, dict) else None


def delete_learning_content(user_id: str, goal_id: int, session_index: int) -> None:
    with _lock:
        _learning_content_cache.pop(_content_key(user_id, goal_id, session_index), None)
        _flush_json(_LEARNING_CONTENT_PATH, _learning_content_cache)


# ---------------- session activity ----------------

def get_session_activity(user_id: str, goal_id: int, session_index: int) -> Optional[Dict[str, Any]]:
    record = _session_activity.get(_content_key(user_id, goal_id, session_index))
    return copy.deepcopy(record) if isinstance(record, dict) else None


def upsert_session_activity(user_id: str, goal_id: int, session_index: int, activity: Dict[str, Any]) -> Dict[str, Any]:
    key = _content_key(user_id, goal_id, session_index)
    with _lock:
        _session_activity[key] = activity
        _flush_json(_SESSION_ACTIVITY_PATH, _session_activity)
        return copy.deepcopy(activity)


# ---------------- mastery history ----------------

def get_mastery_history(user_id: str, goal_id: int) -> List[Dict[str, Any]]:
    history = _mastery_history.get(_mastery_history_key(user_id, goal_id), [])
    return copy.deepcopy(history) if isinstance(history, list) else []


def append_mastery_history(user_id: str, goal_id: int, mastery_rate: float, sample_time: Optional[str] = None) -> List[Dict[str, Any]]:
    key = _mastery_history_key(user_id, goal_id)
    sample = {
        "sample_time": sample_time or _now_iso(),
        "mastery_rate": mastery_rate,
    }
    with _lock:
        _mastery_history.setdefault(key, []).append(sample)
        _mastery_history[key] = _mastery_history[key][-200:]
        _flush_json(_MASTERY_HISTORY_PATH, _mastery_history)
        return copy.deepcopy(_mastery_history[key])


_PROFICIENCY_ORDER = ["unlearned", "beginner", "intermediate", "advanced", "expert"]


def merge_shared_profile_fields(user_id: str, target_goal_id: int) -> Optional[Dict[str, Any]]:
    """Merge mastered_skills, learning_preferences, and behavioral_patterns across goal profiles."""
    all_profiles = get_all_profiles_for_user(user_id)
    target_profile = all_profiles.get(target_goal_id)
    if target_profile is None:
        return None

    merged_mastered: Dict[str, Dict[str, Any]] = {}
    for skill in target_profile.get("cognitive_status", {}).get("mastered_skills", []):
        name = skill.get("name")
        if name:
            merged_mastered[name] = dict(skill)

    for gid, profile in all_profiles.items():
        if gid == target_goal_id:
            continue
        for skill in profile.get("cognitive_status", {}).get("mastered_skills", []):
            name = skill.get("name")
            if not name:
                continue
            existing = merged_mastered.get(name)
            if existing is None:
                merged_mastered[name] = dict(skill)
            else:
                existing_level = existing.get("proficiency_level", "unlearned")
                new_level = skill.get("proficiency_level", "unlearned")
                try:
                    existing_idx = _PROFICIENCY_ORDER.index(existing_level)
                except ValueError:
                    existing_idx = 0
                try:
                    new_idx = _PROFICIENCY_ORDER.index(new_level)
                except ValueError:
                    new_idx = 0
                if new_idx > existing_idx:
                    merged_mastered[name] = dict(skill)

    target_prefs = target_profile.get("learning_preferences")
    target_behavioral = target_profile.get("behavioral_patterns")
    target_learner_info = copy.deepcopy(target_profile.get("learner_information", ""))
    for gid, profile in all_profiles.items():
        if gid == target_goal_id:
            continue

        other_prefs = profile.get("learning_preferences")
        if other_prefs and not target_prefs:
            target_prefs = other_prefs
        elif other_prefs and target_prefs:
            for key, value in other_prefs.items():
                if key not in target_prefs or not target_prefs[key]:
                    target_prefs[key] = value
                elif key in ("fslsm_dimensions", "additional_notes"):
                    if value:
                        target_prefs[key] = value
                elif isinstance(value, dict) and isinstance(target_prefs.get(key), dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in target_prefs[key]:
                            target_prefs[key][sub_key] = sub_value

        other_behavioral = profile.get("behavioral_patterns")
        if other_behavioral and not target_behavioral:
            target_behavioral = other_behavioral
        elif other_behavioral and target_behavioral:
            for key, value in other_behavioral.items():
                if key not in target_behavioral or not target_behavioral[key]:
                    target_behavioral[key] = value

    if "cognitive_status" not in target_profile:
        target_profile["cognitive_status"] = {}
    target_profile["cognitive_status"]["mastered_skills"] = list(merged_mastered.values())

    if target_learner_info:
        target_profile["learner_information"] = target_learner_info
    if target_prefs is not None:
        target_profile["learning_preferences"] = target_prefs
    if target_behavioral is not None:
        target_profile["behavioral_patterns"] = target_behavioral

    mastered_names = set(merged_mastered.keys())
    in_progress = target_profile.get("cognitive_status", {}).get("in_progress_skills", [])
    in_progress = [s for s in in_progress if s.get("name") not in mastered_names]
    target_profile["cognitive_status"]["in_progress_skills"] = in_progress

    num_mastered = len(merged_mastered)
    num_in_progress = len(in_progress)
    total = num_mastered + num_in_progress
    target_profile["cognitive_status"]["overall_progress"] = round(num_mastered / total * 100, 1) if total > 0 else 0.0

    upsert_profile(user_id, target_goal_id, target_profile)
    return target_profile


def propagate_learner_information_to_all_goals(user_id: str, learner_information: str) -> int:
    """Set learner_information identically across all stored profiles for a user."""
    prefix = f"{user_id}:"
    updated_count = 0
    with _lock:
        for key, profile in list(_profiles.items()):
            if not key.startswith(prefix):
                continue
            if not isinstance(profile, dict):
                continue
            updated_profile = copy.deepcopy(profile)
            updated_profile["learner_information"] = str(learner_information or "")
            _profiles[key] = updated_profile
            updated_count += 1
        if updated_count > 0:
            _flush_json(_PROFILES_PATH, _profiles)
    return updated_count


def delete_all_user_data(user_id: str):
    with _lock:
        prefix = f"{user_id}:"
        for store_dict, path in (
            (_profiles, _PROFILES_PATH),
            (_profile_snapshots, _PROFILE_SNAPSHOTS_PATH),
            (_goals, _GOALS_PATH),
            (_learning_content_cache, _LEARNING_CONTENT_PATH),
            (_session_activity, _SESSION_ACTIVITY_PATH),
            (_mastery_history, _MASTERY_HISTORY_PATH),
        ):
            keys_to_remove = [k for k in store_dict if str(k).startswith(prefix)]
            for k in keys_to_remove:
                del store_dict[k]
            _flush_json(path, store_dict)

        _events.pop(user_id, None)
        _flush_json(_EVENTS_PATH, _events)
