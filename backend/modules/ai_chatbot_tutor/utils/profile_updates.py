from __future__ import annotations

import copy
from typing import Any, Callable, Dict, Optional, Tuple


def cap_profile_fslsm_delta(
    old_profile: Dict[str, Any],
    new_profile: Dict[str, Any],
    max_abs_delta: float,
) -> Dict[str, Any]:
    """Limit per-update FSLSM movement to avoid large jumps from a single interaction."""
    if max_abs_delta <= 0:
        return new_profile
    if not isinstance(new_profile, dict):
        return {}

    result = copy.deepcopy(new_profile)
    old_dims = (
        (old_profile or {})
        .get("learning_preferences", {})
        .get("fslsm_dimensions", {})
    )
    new_dims = (
        result.setdefault("learning_preferences", {})
        .setdefault("fslsm_dimensions", {})
    )
    if not isinstance(old_dims, dict):
        old_dims = {}
    if not isinstance(new_dims, dict):
        new_dims = {}

    fslsm_keys = (
        "fslsm_processing",
        "fslsm_perception",
        "fslsm_input",
        "fslsm_understanding",
    )

    for key in fslsm_keys:
        try:
            old_val = float(old_dims.get(key, 0.0))
        except Exception:
            old_val = 0.0
        try:
            proposed = float(new_dims.get(key, old_val))
        except Exception:
            proposed = old_val
        upper = old_val + max_abs_delta
        lower = old_val - max_abs_delta
        capped = max(lower, min(upper, proposed))
        capped = max(-1.0, min(1.0, capped))
        new_dims[key] = round(capped, 6)

    result["learning_preferences"]["fslsm_dimensions"] = new_dims
    return result


def safe_update_learning_preferences(
    llm: Any,
    *,
    learner_interactions: Any,
    learner_information: Any = "",
    user_id: Optional[str] = None,
    goal_id: Optional[int] = None,
    learner_profile: Optional[Dict[str, Any]] = None,
    max_fslsm_delta: Optional[float] = None,
    get_profile_fn: Callable[[str, int], Optional[Dict[str, Any]]],
    save_snapshot_fn: Callable[[str, int, Dict[str, Any]], None],
    record_snapshot_timestamp_fn: Callable[[str, int], None],
    update_learning_preferences_fn: Callable[[Any, Any, Any, Any], Dict[str, Any]],
    reset_adaptation_on_sign_flip_fn: Callable[[str, int, Dict[str, Any], Dict[str, Any]], None],
    upsert_profile_fn: Callable[[str, int, Dict[str, Any]], None],
    refresh_goal_profile_fn: Callable[[str, int], Dict[str, Any]],
) -> Tuple[Dict[str, Any], bool]:
    """Safely update learning preferences and preserve adaptation invariants.

    Uses snapshot + sign-flip reset when user/goal context is available.
    """
    base_profile = learner_profile if isinstance(learner_profile, dict) else {}
    old_profile_for_reset = copy.deepcopy(base_profile)
    input_profile = copy.deepcopy(base_profile)

    if user_id is not None and goal_id is not None:
        stored_profile = get_profile_fn(user_id, goal_id)
        if isinstance(stored_profile, dict):
            input_profile = copy.deepcopy(stored_profile)
            old_profile_for_reset = copy.deepcopy(stored_profile)
        save_snapshot_fn(user_id, goal_id, old_profile_for_reset)
        record_snapshot_timestamp_fn(user_id, goal_id)

    updated_profile = update_learning_preferences_fn(
        llm,
        input_profile,
        learner_interactions,
        learner_information if learner_information is not None else "",
    )
    if not isinstance(updated_profile, dict):
        updated_profile = {}
    if isinstance(max_fslsm_delta, (int, float)) and max_fslsm_delta > 0:
        updated_profile = cap_profile_fslsm_delta(
            old_profile_for_reset if isinstance(old_profile_for_reset, dict) else {},
            updated_profile,
            float(max_fslsm_delta),
        )

    if user_id is not None and goal_id is not None:
        reset_adaptation_on_sign_flip_fn(
            user_id,
            goal_id,
            old_profile_for_reset,
            updated_profile,
        )
        upsert_profile_fn(user_id, goal_id, updated_profile)
        merged = refresh_goal_profile_fn(user_id, goal_id)
        profile_updated = merged != old_profile_for_reset
        return merged, profile_updated

    profile_updated = updated_profile != old_profile_for_reset
    return updated_profile, profile_updated
