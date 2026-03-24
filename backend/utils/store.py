"""Azure Cosmos DB-backed persistence for learner profiles, goals, content, and activity.

Replaces the previous JSON file-backed implementation. All public function
signatures are preserved so callers in main.py require no changes.

Key design notes:
- The Cosmos DB `id` field must be a string; goals previously used an integer
  `id`. We store the integer as `goal_id` and use a composite string
  `"{user_id}:{goal_id}"` as the Cosmos `id`. _strip_goal_cosmos_fields()
  reverses this on every read so callers continue to see goal["id"] as an int.
- Threading locks are removed; Cosmos DB handles concurrent HTTP requests natively.
- In-memory caching is removed; every read hits Cosmos DB directly.
- load() is now a connection health-check called once at startup.
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from modules.learner_profiler.schemas import refresh_learning_preferences_derived_fields

logger = logging.getLogger(__name__)

# Module-level Cosmos DB client. Initialised by load() at FastAPI startup.
_cosmos: Optional[Any] = None  # CosmosUserStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def load() -> None:
    """Initialise the Cosmos DB connection. Called once at FastAPI startup."""
    global _cosmos
    from base.cosmos_client import CosmosUserStore
    try:
        _cosmos = CosmosUserStore.from_env()
        if not _cosmos.check_connection():
            logger.warning("Cosmos DB connection check failed — store will raise on first use")
    except ValueError as exc:
        logger.warning("Cosmos DB not configured: %s. Store unavailable.", exc)
        _cosmos = None


def _get_cosmos():
    """Return the Cosmos DB client, raising RuntimeError if not initialised."""
    if _cosmos is None:
        raise RuntimeError(
            "Cosmos DB client not initialised. "
            "Ensure AZURE_COSMOS_CONNECTION_STRING is set and store.load() was called."
        )
    return _cosmos


# ---------------------------------------------------------------------------
# Field-stripping helpers
# ---------------------------------------------------------------------------

def _strip(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip Cosmos system fields from a returned item."""
    from base.cosmos_client import strip_cosmos_fields
    return strip_cosmos_fields(item)


# Routing fields injected by the storage layer for Cosmos partitioning.
# These are not part of the application data model and are stripped on read
# for profile-type containers (profiles, profile_snapshots) to maintain
# backward compatibility with callers that store/retrieve plain dicts.
_PROFILE_ROUTING_FIELDS = {"id", "user_id", "goal_id"}


def _strip_profile(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip Cosmos system + routing fields from a profile or snapshot item."""
    clean = _strip(item)
    for f in _PROFILE_ROUTING_FIELDS:
        clean.pop(f, None)
    return clean


def _strip_goal(item: Dict[str, Any]) -> Dict[str, Any]:
    """Strip Cosmos system fields and restore the integer goal id.

    Goals are stored with Cosmos `id` = "{user_id}:{goal_id}" and an integer
    `goal_id` field. This helper swaps them back so callers see goal["id"] as int.
    """
    clean = _strip(item)
    clean["id"] = clean.pop("goal_id")
    return clean


# ---------------------------------------------------------------------------
# Composite key helpers (mirrors old file-key patterns)
# ---------------------------------------------------------------------------

def _profile_key(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def _goal_cosmos_id(user_id: str, goal_id: int) -> str:
    return f"{user_id}:{goal_id}"


def _content_key(user_id: str, goal_id: int, session_index: int) -> str:
    return f"{user_id}:{goal_id}:{session_index}"


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def upsert_profile(user_id: str, goal_id: int, profile: Dict[str, Any]) -> None:
    refresh_learning_preferences_derived_fields(profile)
    item = dict(profile)
    item["id"] = _profile_key(user_id, goal_id)
    item["user_id"] = user_id
    item["goal_id"] = goal_id
    _get_cosmos().upsert("profiles", item)


def get_profile(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    item = _get_cosmos().get("profiles", _profile_key(user_id, goal_id), user_id)
    return _strip_profile(item) if item is not None else None


def get_all_profiles_for_user(user_id: str) -> Dict[int, Dict[str, Any]]:
    items = _get_cosmos().query(
        "profiles",
        "SELECT * FROM c WHERE c.user_id = @uid",
        [{"name": "@uid", "value": user_id}],
        partition_key_value=user_id,
    )
    result: Dict[int, Dict[str, Any]] = {}
    for item in items:
        gid = item.get("goal_id")  # extract before stripping
        if isinstance(gid, int):
            result[gid] = _strip_profile(item)
    return result


def seed_new_goal_profile_shared_fields(user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Copy shared preference fields from any existing goal into a new goal profile.

    New-goal creation should inherit the learner's current FSLSM dimensions and
    behavioral patterns rather than keeping the profiler's fresh baseline values.
    """
    seeded = copy.deepcopy(profile) if isinstance(profile, dict) else {}
    if not seeded:
        return seeded

    source_prefs = None
    source_behavioral = None
    for existing in get_all_profiles_for_user(user_id).values():
        if source_prefs is None and isinstance(existing.get("learning_preferences"), dict):
            source_prefs = copy.deepcopy(existing.get("learning_preferences"))
        if source_behavioral is None and isinstance(existing.get("behavioral_patterns"), dict):
            source_behavioral = copy.deepcopy(existing.get("behavioral_patterns"))
        if source_prefs is not None and source_behavioral is not None:
            break

    if source_prefs is not None:
        seeded["learning_preferences"] = source_prefs
    if source_behavioral is not None:
        seeded["behavioral_patterns"] = source_behavioral
    return seeded


# ---------------------------------------------------------------------------
# Profile snapshots (pre-update copies used for adaptation comparison)
# ---------------------------------------------------------------------------

def save_profile_snapshot(user_id: str, goal_id: int, profile: Dict[str, Any]) -> None:
    item = dict(profile)
    item["id"] = _profile_key(user_id, goal_id)
    item["user_id"] = user_id
    item["goal_id"] = goal_id
    _get_cosmos().upsert("profile_snapshots", item)


def get_profile_snapshot(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    item = _get_cosmos().get("profile_snapshots", _profile_key(user_id, goal_id), user_id)
    return _strip_profile(item) if item is not None else None


def delete_profile_snapshot(user_id: str, goal_id: int) -> None:
    _get_cosmos().delete("profile_snapshots", _profile_key(user_id, goal_id), user_id)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def append_event(user_id: str, event: Dict[str, Any]) -> None:
    db = _get_cosmos()
    existing = db.get("events", user_id, user_id)
    entries: List[Dict[str, Any]] = existing.get("entries", []) if existing else []
    entries.append(event)
    entries = entries[-200:]
    db.upsert("events", {"id": user_id, "user_id": user_id, "entries": entries})


def get_events(user_id: str) -> List[Dict[str, Any]]:
    item = _get_cosmos().get("events", user_id, user_id)
    return list(item.get("entries", [])) if item is not None else []


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

def _next_goal_id_for_user(user_id: str) -> int:
    items = _get_cosmos().query(
        "goals",
        "SELECT c.goal_id FROM c WHERE c.user_id = @uid",
        [{"name": "@uid", "value": user_id}],
        partition_key_value=user_id,
    )
    ids = [i.get("goal_id") for i in items if isinstance(i.get("goal_id"), int)]
    return (max(ids) + 1) if ids else 0


def create_goal(user_id: str, goal_payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    goal_id = _next_goal_id_for_user(user_id)
    goal: Dict[str, Any] = {
        # Cosmos id (string composite) + integer goal_id for callers
        "id": _goal_cosmos_id(user_id, goal_id),
        "goal_id": goal_id,
        "user_id": user_id,
        "learning_goal": goal_payload.get("learning_goal", ""),
        "goal_display_name": goal_payload.get("goal_display_name", ""),
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
    _get_cosmos().upsert("goals", goal)
    # Return a copy with integer id (as callers expect)
    return _strip_goal(dict(goal))


def get_goal(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    item = _get_cosmos().get("goals", _goal_cosmos_id(user_id, goal_id), user_id)
    return _strip_goal(item) if item is not None else None


def get_all_goals_for_user(
    user_id: str, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    if include_deleted:
        q = "SELECT * FROM c WHERE c.user_id = @uid"
    else:
        q = (
            "SELECT * FROM c WHERE c.user_id = @uid"
            " AND (c.is_deleted = false OR NOT IS_DEFINED(c.is_deleted))"
        )
    items = _get_cosmos().query(
        "goals",
        q,
        [{"name": "@uid", "value": user_id}],
        partition_key_value=user_id,
    )
    goals = [_strip_goal(i) for i in items]
    goals.sort(key=lambda g: g.get("id", 0))  # id is int after _strip_goal
    return goals


def patch_goal(
    user_id: str, goal_id: int, updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    cosmos_id = _goal_cosmos_id(user_id, goal_id)
    existing = _get_cosmos().get("goals", cosmos_id, user_id)
    if existing is None:
        return None
    # Protect immutable fields; also protect goal_id (internal Cosmos field)
    safe = {
        k: v
        for k, v in updates.items()
        if k not in {"id", "user_id", "created_at", "goal_id"}
    }
    safe["updated_at"] = _now_iso()
    patch_ops = [{"op": "set", "path": f"/{k}", "value": v} for k, v in safe.items()]
    updated = _get_cosmos().patch("goals", cosmos_id, user_id, patch_ops)
    return _strip_goal(updated)


def delete_goal(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    return patch_goal(user_id, goal_id, {"is_deleted": True})


def list_goal_aggregates(
    user_id: str, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    return [
        assemble_goal_aggregate(user_id, goal)
        for goal in get_all_goals_for_user(user_id, include_deleted=include_deleted)
    ]


def get_goal_aggregate(user_id: str, goal_id: int) -> Optional[Dict[str, Any]]:
    goal = get_goal(user_id, goal_id)
    if not goal:
        return None
    return assemble_goal_aggregate(user_id, goal)


def assemble_goal_aggregate(user_id: str, goal: Dict[str, Any]) -> Dict[str, Any]:
    aggregate = copy.deepcopy(goal)
    profile = get_profile(user_id, int(goal.get("id", 0))) or {}
    aggregate["learner_profile"] = profile
    if not aggregate.get("goal_display_name"):
        aggregate["goal_display_name"] = profile.get("goal_display_name", "")
    return aggregate


# ---------------------------------------------------------------------------
# Learning content cache
# ---------------------------------------------------------------------------

def upsert_learning_content(
    user_id: str, goal_id: int, session_index: int, learning_content: Dict[str, Any]
) -> Dict[str, Any]:
    key = _content_key(user_id, goal_id, session_index)
    now = _now_iso()
    # Preserve created_at from existing record if present
    existing = _get_cosmos().get("learning_content", key, user_id)
    record: Dict[str, Any] = {
        "id": key,
        "user_id": user_id,
        "goal_id": goal_id,
        "session_index": session_index,
        "learning_content": learning_content,
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    _get_cosmos().upsert("learning_content", record)
    return _strip(dict(record))


def get_learning_content(
    user_id: str, goal_id: int, session_index: int
) -> Optional[Dict[str, Any]]:
    item = _get_cosmos().get(
        "learning_content", _content_key(user_id, goal_id, session_index), user_id
    )
    return _strip(item) if item is not None else None


def delete_learning_content(user_id: str, goal_id: int, session_index: int) -> None:
    _get_cosmos().delete(
        "learning_content", _content_key(user_id, goal_id, session_index), user_id
    )


# ---------------------------------------------------------------------------
# Session activity
# ---------------------------------------------------------------------------

def get_session_activity(
    user_id: str, goal_id: int, session_index: int
) -> Optional[Dict[str, Any]]:
    item = _get_cosmos().get(
        "session_activity", _content_key(user_id, goal_id, session_index), user_id
    )
    return _strip(item) if item is not None else None


def upsert_session_activity(
    user_id: str, goal_id: int, session_index: int, activity: Dict[str, Any]
) -> Dict[str, Any]:
    key = _content_key(user_id, goal_id, session_index)
    # Inject partition/routing fields so the item is queryable by user_id
    item = dict(activity)
    item["id"] = key
    item["user_id"] = user_id
    item["goal_id"] = goal_id
    item["session_index"] = session_index
    _get_cosmos().upsert("session_activity", item)
    return _strip(item)


# ---------------------------------------------------------------------------
# Mastery history
# ---------------------------------------------------------------------------

def get_mastery_history(user_id: str, goal_id: int) -> List[Dict[str, Any]]:
    key = _profile_key(user_id, goal_id)
    item = _get_cosmos().get("mastery_history", key, user_id)
    return list(item.get("entries", [])) if item is not None else []


def append_mastery_history(
    user_id: str,
    goal_id: int,
    mastery_rate: float,
    sample_time: Optional[str] = None,
) -> List[Dict[str, Any]]:
    key = _profile_key(user_id, goal_id)
    sample = {"sample_time": sample_time or _now_iso(), "mastery_rate": mastery_rate}
    db = _get_cosmos()
    existing = db.get("mastery_history", key, user_id)
    entries: List[Dict[str, Any]] = existing.get("entries", []) if existing else []
    entries.append(sample)
    entries = entries[-200:]
    db.upsert(
        "mastery_history",
        {"id": key, "user_id": user_id, "goal_id": goal_id, "entries": entries},
    )
    return list(entries)


# ---------------------------------------------------------------------------
# Cross-goal operations
# ---------------------------------------------------------------------------

# ---------------- bias audit log ----------------

def append_bias_audit_log(
    user_id: str,
    goal_id: Optional[int],
    audit_type: str,
    audit_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Append a compact bias audit entry. Retains last 200 per user (Cosmos DB)."""
    flags = audit_result.get("flags") or audit_result.get("flagged_items") or []
    flagged = [f for f in flags if isinstance(f, dict)]
    audited_items = audit_result.get("audited_items") or audit_result.get("items_audited")
    audited_count = int(audited_items) if audited_items is not None else len(flagged)

    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "goal_id": goal_id,
        "audit_type": audit_type,
        "overall_risk": str(audit_result.get("overall_risk", "low")).lower(),
        "flagged_count": len(flagged),
        "audited_count": audited_count,
        "flags_summary": [
            {"category": f.get("category", "unknown"), "severity": f.get("severity", "low")}
            for f in flagged[:20]
        ],
    }
    db = _get_cosmos()
    existing = db.get("bias_audit_log", user_id, user_id)
    entries: List[Dict[str, Any]] = existing.get("entries", []) if existing else []
    entries.append(entry)
    entries = entries[-200:]
    db.upsert("bias_audit_log", {"id": user_id, "user_id": user_id, "entries": entries})
    return list(entries)


def get_bias_audit_log(user_id: str, goal_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return all bias audit entries for a user, optionally filtered by goal_id."""
    item = _get_cosmos().get("bias_audit_log", user_id, user_id)
    entries = copy.deepcopy(item.get("entries", [])) if item is not None else []
    if goal_id is not None:
        entries = [e for e in entries if e.get("goal_id") == goal_id]
    return entries


_PROFICIENCY_ORDER = ["unlearned", "beginner", "intermediate", "advanced", "expert"]


def merge_shared_profile_fields(
    user_id: str, target_goal_id: int
) -> Optional[Dict[str, Any]]:
    """Merge mastered_skills, learning_preferences, and behavioral_patterns across profiles."""
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
    target_profile["cognitive_status"]["overall_progress"] = (
        round(num_mastered / total * 100, 1) if total > 0 else 0.0
    )

    upsert_profile(user_id, target_goal_id, target_profile)
    return target_profile


def propagate_learning_preferences_to_other_goals(
    user_id: str, source_goal_id: int
) -> None:
    """Push learning_preferences and behavioral_patterns from source goal to all other goals."""
    all_profiles = get_all_profiles_for_user(user_id)
    source_profile = all_profiles.get(source_goal_id)
    if source_profile is None:
        return
    source_prefs = source_profile.get("learning_preferences")
    source_behavioral = source_profile.get("behavioral_patterns")
    for goal_id, profile in all_profiles.items():
        if goal_id == source_goal_id:
            continue
        changed = False
        if source_prefs is not None:
            profile["learning_preferences"] = copy.deepcopy(source_prefs)
            changed = True
        if source_behavioral is not None:
            profile["behavioral_patterns"] = copy.deepcopy(source_behavioral)
            changed = True
        if changed:
            upsert_profile(user_id, goal_id, profile)


def propagate_learner_information_to_all_goals(
    user_id: str, learner_information: str
) -> int:
    """Set learner_information identically across all stored profiles for a user."""
    all_profiles = get_all_profiles_for_user(user_id)
    count = 0
    for goal_id, profile in all_profiles.items():
        profile["learner_information"] = str(learner_information or "")
        upsert_profile(user_id, int(goal_id), profile)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Bulk deletion
# ---------------------------------------------------------------------------

def delete_all_user_data(user_id: str) -> None:
    """Delete all stored data for *user_id* across all containers.

    Used by "Restart Onboarding" and account deletion flows. Does NOT remove
    the auth record — call auth_store.delete_user() for that.
    """
    db = _get_cosmos()
    containers = [
        "profiles",
        "profile_snapshots",
        "goals",
        "learning_content",
        "session_activity",
        "mastery_history",
        "events",
        "bias_audit_log",
    ]
    for container in containers:
        items = db.query(
            container,
            "SELECT c.id FROM c WHERE c.user_id = @uid",
            [{"name": "@uid", "value": user_id}],
            partition_key_value=user_id,
        )
        for item in items:
            db.delete(container, item["id"], user_id)
