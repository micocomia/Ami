"""JSON file-backed persistence for learner profiles and behavior events."""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"
_PROFILES_PATH = _DATA_DIR / "profiles.json"
_EVENTS_PATH = _DATA_DIR / "events.json"
_USER_STATES_PATH = _DATA_DIR / "user_states.json"
_PROFILE_SNAPSHOTS_PATH = _DATA_DIR / "profile_snapshots.json"

_lock = threading.Lock()

# keyed by "{user_id}:{goal_id}"
_profiles: Dict[str, Dict[str, Any]] = {}
# keyed by user_id
_events: Dict[str, List[Dict[str, Any]]] = {}
# keyed by user_id — generic UI state blob per user
_user_states: Dict[str, Dict[str, Any]] = {}
# keyed by "{user_id}:{goal_id}" — pre-update snapshots for adapt comparison
_profile_snapshots: Dict[str, Dict[str, Any]] = {}


def load():
    """Read persisted data from disk into memory. Call once at startup."""
    global _profiles, _events, _user_states, _profile_snapshots
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _PROFILES_PATH.exists():
        try:
            _profiles = json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _profiles = {}
    if _EVENTS_PATH.exists():
        try:
            _events = json.loads(_EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            _events = {}
    if _USER_STATES_PATH.exists():
        try:
            _user_states = json.loads(_USER_STATES_PATH.read_text(encoding="utf-8"))
        except Exception:
            _user_states = {}
    if _PROFILE_SNAPSHOTS_PATH.exists():
        try:
            _profile_snapshots = json.loads(_PROFILE_SNAPSHOTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            _profile_snapshots = {}


def _flush_profiles():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PROFILES_PATH.write_text(json.dumps(_profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def _flush_snapshots():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PROFILE_SNAPSHOTS_PATH.write_text(
        json.dumps(_profile_snapshots, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _flush_events():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _EVENTS_PATH.write_text(json.dumps(_events, ensure_ascii=False, indent=2), encoding="utf-8")


def _profile_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def upsert_profile(user_id: str, goal_id: int, profile: Dict[str, Any]):
    with _lock:
        _profiles[_profile_key(user_id, goal_id)] = profile
        _flush_profiles()


def get_profile(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return _profiles.get(_profile_key(user_id, goal_id))


def get_all_profiles_for_user(user_id: str) -> Dict[int, Dict[str, Any]]:
    prefix = f"{user_id}:"
    result = {}
    for key, profile in _profiles.items():
        if key.startswith(prefix):
            gid = key[len(prefix):]
            try:
                result[int(gid)] = profile
            except ValueError:
                result[gid] = profile
    return result


def save_profile_snapshot(user_id: str, goal_id: int, profile: Dict[str, Any]):
    with _lock:
        _profile_snapshots[_profile_key(user_id, goal_id)] = profile
        _flush_snapshots()


def get_profile_snapshot(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return _profile_snapshots.get(_profile_key(user_id, goal_id))


def delete_profile_snapshot(user_id: str, goal_id: int):
    with _lock:
        _profile_snapshots.pop(_profile_key(user_id, goal_id), None)
        _flush_snapshots()


def append_event(user_id: str, event: Dict[str, Any]):
    with _lock:
        _events.setdefault(user_id, []).append(event)
        _events[user_id] = _events[user_id][-200:]
        _flush_events()


def get_events(user_id: str) -> List[Dict[str, Any]]:
    return _events.get(user_id, [])


# --------------- user states (generic UI state per user) ---------------

def _flush_user_states():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USER_STATES_PATH.write_text(json.dumps(_user_states, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_state(user_id: str) -> Optional[Dict[str, Any]]:
    return _user_states.get(user_id)


def put_user_state(user_id: str, state: Dict[str, Any]):
    with _lock:
        _user_states[user_id] = state
        _flush_user_states()


def delete_user_state(user_id: str):
    with _lock:
        _user_states.pop(user_id, None)
        _flush_user_states()


_PROFICIENCY_ORDER = ["unlearned", "beginner", "intermediate", "advanced", "expert"]


def merge_shared_profile_fields(user_id: str, target_goal_id: int) -> Optional[Dict[str, Any]]:
    """Merge mastered_skills, learning_preferences, and behavioral_patterns
    from all of a user's goal profiles into the target goal's profile.

    - mastered_skills: union across all goals (highest proficiency per skill name)
    - learning_preferences: overwrite with values from another goal if target has none
    - behavioral_patterns: same as preferences
    - in_progress_skills: remove any skill now in mastered_skills
    - overall_progress: recalculate as mastered / (mastered + in_progress) * 100

    Persists the merged profile and returns it.
    Returns None if no profile exists for the target goal.
    """
    all_profiles = get_all_profiles_for_user(user_id)
    target_profile = all_profiles.get(target_goal_id)
    if target_profile is None:
        return None

    # Build union of mastered_skills across all goals (highest proficiency wins)
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
                # Keep the higher proficiency
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

    # Propagate learning_preferences and behavioral_patterns from other goals
    target_prefs = target_profile.get("learning_preferences")
    target_behavioral = target_profile.get("behavioral_patterns")
    for gid, profile in all_profiles.items():
        if gid == target_goal_id:
            continue
        other_prefs = profile.get("learning_preferences")
        if other_prefs and not target_prefs:
            target_prefs = other_prefs
        elif other_prefs and target_prefs:
            # Merge: take values from other goal for any missing keys
            for key, value in other_prefs.items():
                if key not in target_prefs or not target_prefs[key]:
                    target_prefs[key] = value
                elif key == "fslsm_dimensions":
                    # FSLSM is unified across all goals; overwrite so updates propagate
                    if isinstance(value, dict) and value:
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

    # Apply merged mastered_skills
    if "cognitive_status" not in target_profile:
        target_profile["cognitive_status"] = {}
    target_profile["cognitive_status"]["mastered_skills"] = list(merged_mastered.values())

    # Apply preferences and behavioral patterns
    if target_prefs is not None:
        target_profile["learning_preferences"] = target_prefs
    if target_behavioral is not None:
        target_profile["behavioral_patterns"] = target_behavioral

    # Remove mastered skills from in_progress_skills
    mastered_names = set(merged_mastered.keys())
    in_progress = target_profile.get("cognitive_status", {}).get("in_progress_skills", [])
    in_progress = [s for s in in_progress if s.get("name") not in mastered_names]
    target_profile["cognitive_status"]["in_progress_skills"] = in_progress

    # Recalculate overall_progress
    num_mastered = len(merged_mastered)
    num_in_progress = len(in_progress)
    total = num_mastered + num_in_progress
    if total > 0:
        target_profile["cognitive_status"]["overall_progress"] = round(
            num_mastered / total * 100, 1
        )
    else:
        target_profile["cognitive_status"]["overall_progress"] = 0.0

    # Persist
    upsert_profile(user_id, target_goal_id, target_profile)
    return target_profile


def delete_all_user_data(user_id: str):
    with _lock:
        # Remove profiles (keyed as "user_id:goal_id")
        prefix = f"{user_id}:"
        keys_to_remove = [k for k in _profiles if k.startswith(prefix)]
        for k in keys_to_remove:
            del _profiles[k]
        _flush_profiles()

        # Remove events
        _events.pop(user_id, None)
        _flush_events()

        # Remove user state
        _user_states.pop(user_id, None)
        _flush_user_states()

        # Remove profile snapshots
        keys_to_remove = [k for k in _profile_snapshots if k.startswith(prefix)]
        for k in keys_to_remove:
            del _profile_snapshots[k]
        _flush_snapshots()
