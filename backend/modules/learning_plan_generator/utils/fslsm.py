from typing import Any, Dict, Mapping, Optional

from utils.quiz_scorer import get_mastery_threshold_for_session


# Default mastery thresholds by proficiency level
_DEFAULT_THRESHOLD_MAP = {
    "beginner": 60,
    "intermediate": 70,
    "advanced": 80,
    "expert": 90,
}

_FSLSM_ACTIVATION_THRESHOLD = 0.7


def _parse_profile(profile: Any) -> Dict[str, Any]:
    """Parse learner_profile into a dict regardless of input type."""
    import json

    if isinstance(profile, dict):
        return profile
    if isinstance(profile, str):
        profile = profile.strip()
        if not profile:
            return {}
        try:
            return json.loads(profile)
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            import ast
            return ast.literal_eval(profile)
        except Exception:
            return {}
    if isinstance(profile, Mapping):
        return dict(profile)
    return {}


def _apply_fslsm_overrides(
    learning_path: Dict[str, Any],
    learner_profile: Dict[str, Any],
    threshold_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Deterministic post-processing: enforce FSLSM structural rules.

    This acts as a safety net — even if the LLM ignores prompt instructions,
    the structural fields are set deterministically based on the learner's
    FSLSM dimensions.
    """
    if threshold_map is None:
        threshold_map = _DEFAULT_THRESHOLD_MAP

    dims = (
        learner_profile
        .get("learning_preferences", {})
        .get("fslsm_dimensions", {})
    )
    threshold = _FSLSM_ACTIVATION_THRESHOLD

    for session in learning_path.get("learning_path", []):
        # Processing dimension: Active (-) vs Reflective (+)
        proc = dims.get("fslsm_processing", 0)
        if proc <= -threshold:
            session["has_checkpoint_challenges"] = True
        elif proc >= threshold:
            session["thinking_time_buffer_minutes"] = max(
                session.get("thinking_time_buffer_minutes", 0), 10
            )

        # Perception dimension: Sensing (-) vs Intuitive (+)
        perc = dims.get("fslsm_perception", 0)
        if perc <= -threshold:
            session["session_sequence_hint"] = "application-first"
        elif perc >= threshold:
            session["session_sequence_hint"] = "theory-first"

        # Understanding dimension: Sequential (-) vs Global (+)
        und = dims.get("fslsm_understanding", 0)
        if und >= threshold:
            session["navigation_mode"] = "free"
        else:
            session["navigation_mode"] = "linear"

        # Per-session mastery threshold based on required proficiency
        session["mastery_threshold"] = get_mastery_threshold_for_session(
            session, threshold_map
        )

    return learning_path
