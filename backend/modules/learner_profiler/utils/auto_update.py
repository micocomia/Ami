"""Utility for auto-updating (or initializing) a learner profile from event data."""

from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple


def auto_update_learner_profile(
    llm: Any,
    user_id: str,
    goal_id: int,
    interactions: Any,
    learning_goal: Optional[str],
    learner_info: Any,
    skill_gaps: Any,
    session_information: Optional[Dict[str, Any]],
    get_profile_fn: Callable[[str, int], Optional[Dict[str, Any]]],
    upsert_profile_fn: Callable[[str, int, Dict[str, Any]], None],
    initialize_fn: Callable,
    update_fn: Callable,
) -> Tuple[str, Dict[str, Any]]:
    """Initialize or update a learner profile.

    Returns (mode, profile) where mode is 'initialized' or 'updated'.
    Raises ValueError if first-time user is missing required params.
    """
    current_profile = get_profile_fn(user_id, goal_id)

    if current_profile is None:
        if not (learning_goal and learner_info is not None and skill_gaps is not None):
            raise ValueError(
                "No profile found for this user_id. Provide learning_goal, "
                "learner_information, and skill_gaps to initialize."
            )
        profile = initialize_fn(llm, learning_goal, learner_info, skill_gaps)
        upsert_profile_fn(user_id, goal_id, profile)
        return "initialized", profile

    session_info = session_information or {}
    session_info = {
        **session_info,
        "updated_at": datetime.utcnow().isoformat(),
        "event_count": len(interactions) if hasattr(interactions, "__len__") else 0,
        "source": "EVENT_STORE",
    }
    updated_profile = update_fn(
        llm,
        current_profile,
        interactions,
        learner_info if learner_info is not None else "",
        session_info,
    )
    upsert_profile_fn(user_id, goal_id, updated_profile)
    return "updated", updated_profile
