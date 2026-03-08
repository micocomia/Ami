"""Utility for computing behavioral/learning metrics from session activity data."""

from typing import Any, Callable, Dict, List, Optional


def compute_behavioral_metrics(
    user_id: str,
    goal_id: Optional[int],
    idle_timeout_secs: int,
    get_all_goals_fn: Callable[[str], List[Dict[str, Any]]],
    get_session_activity_fn: Callable[[str, int, int], Optional[Dict[str, Any]]],
    get_mastery_history_fn: Callable[[str, Optional[int]], List[Dict[str, Any]]],
    sum_activity_duration_fn: Callable[[Optional[Dict[str, Any]], int], float],
) -> Dict[str, Any]:
    """Aggregate session durations, mastery history, and motivational triggers for a user.

    Returns the behavioral metrics dict (matches BehavioralMetricsResponse shape).
    Raises ValueError if no goals are found for the user.
    """
    goals = get_all_goals_fn(user_id)
    if not goals:
        raise ValueError(f"No goals found for user_id={user_id!r}")

    completed_durations: List[float] = []
    total_triggers = 0

    for goal in goals:
        gid = goal.get("id")
        if goal_id is not None and gid != goal_id:
            continue
        for idx, _session in enumerate(goal.get("learning_path", [])):
            activity = get_session_activity_fn(user_id, gid, idx)
            if not isinstance(activity, dict):
                continue
            duration = sum_activity_duration_fn(activity, idle_timeout_secs)
            if duration > 0:
                completed_durations.append(duration)
            triggers = activity.get("trigger_events", [])
            if isinstance(triggers, list):
                total_triggers += len(triggers)

    total_in_path = 0
    sessions_learned = 0
    if goal_id is not None:
        for g in goals:
            if isinstance(g, dict) and g.get("id") == goal_id:
                path = g.get("learning_path", [])
                total_in_path = len(path)
                sessions_learned = sum(
                    1 for s in path if isinstance(s, dict) and s.get("if_learned")
                )
                break

    history = get_mastery_history_fn(user_id, goal_id) if goal_id is not None else []
    history_rates = [
        float(item.get("mastery_rate", 0.0)) for item in history if isinstance(item, dict)
    ]

    total_duration = sum(completed_durations)
    avg_duration = total_duration / len(completed_durations) if completed_durations else 0.0

    return {
        "user_id": user_id,
        "goal_id": goal_id,
        "sessions_completed": len(completed_durations),
        "total_sessions_in_path": total_in_path,
        "sessions_learned": sessions_learned,
        "avg_session_duration_sec": round(avg_duration, 1),
        "total_learning_time_sec": round(total_duration, 1),
        "motivational_triggers_count": total_triggers,
        "mastery_history": history_rates,
        "latest_mastery_rate": history_rates[-1] if history_rates else None,
    }
