from typing import Any, Dict, Mapping, Optional, Sequence, Union
import json

from pydantic import BaseModel, Field

from base import BaseAgent
from modules.learning_plan_generator.schemas import LearningPath
from modules.learning_plan_generator.prompts.learning_path_scheduling import (
    learning_path_scheduler_system_prompt,
    learning_path_scheduler_task_prompt_reflexion,
    learning_path_scheduler_task_prompt_reschedule,
    learning_path_scheduler_task_prompt_session,
)
from utils.quiz_scorer import get_mastery_threshold_for_session


JSONDict = Dict[str, Any]

# Default mastery thresholds by proficiency level
_DEFAULT_THRESHOLD_MAP = {
    "beginner": 60,
    "intermediate": 70,
    "advanced": 80,
    "expert": 90,
}

_FSLSM_ACTIVATION_THRESHOLD = 0.3


def _parse_profile(profile: Any) -> Dict[str, Any]:
    """Parse learner_profile into a dict regardless of input type."""
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


class SessionSchedulePayload(BaseModel):
    """Input payload for scheduling sessions (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    session_count: int = 0


class LearningPathRefinementPayload(BaseModel):
    """Input payload for reflexion/refinement of a learning path (validated)."""

    learning_path: Sequence[Any]
    feedback: Union[str, Dict[str, Any], Mapping[str, Any]]


class LearningPathReschedulePayload(BaseModel):
    """Input payload for rescheduling an existing learning path (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    learning_path: Sequence[Any]
    session_count: Optional[Union[int, str]] = None
    other_feedback: Optional[Union[str, Dict[str, Any], Mapping[str, Any]]] = None


class LearningPathScheduler(BaseAgent):
    """High-level agent orchestrating learning path scheduling tasks."""

    name: str = "LearningPathScheduler"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=learning_path_scheduler_system_prompt,
            jsonalize_output=True,
        )

    def schedule_session(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Schedule sessions based on learner profile and desired count."""
        payload_dict = SessionSchedulePayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_session
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearningPath.model_validate(raw_output)
        result = validated_output.model_dump()
        # Apply FSLSM overrides deterministically
        profile = _parse_profile(input_dict.get("learner_profile", {}))
        return _apply_fslsm_overrides(result, profile)

    def reflexion(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Refine the learning path based on evaluator feedback."""
        payload_dict = LearningPathRefinementPayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_reflexion
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated = LearningPath.model_validate(raw_output)
        result = validated.model_dump()
        # Apply FSLSM overrides if profile available in feedback
        feedback = input_dict.get("feedback", {})
        if isinstance(feedback, dict) and "learner_profile" in feedback:
            profile = _parse_profile(feedback["learner_profile"])
            result = _apply_fslsm_overrides(result, profile)
        return result

    def reschedule(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Reschedule the learning path with optional new session_count/feedback."""

        payload_dict = LearningPathReschedulePayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_reschedule
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated = LearningPath.model_validate(raw_output)
        result = validated.model_dump()
        # Apply FSLSM overrides
        profile = _parse_profile(input_dict.get("learner_profile", {}))
        return _apply_fslsm_overrides(result, profile)


def schedule_learning_path_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    session_count: int = 0,
) -> JSONDict:
    """Convenience helper to create a scheduler and produce a new learning path."""

    learning_path_scheduler = LearningPathScheduler(llm)
    payload_dict = {
        "learner_profile": learner_profile,
        "session_count": session_count,
    }
    return learning_path_scheduler.schedule_session(payload_dict)


def reschedule_learning_path_with_llm(
    llm: Any,
    learning_path: Sequence[Any],
    learner_profile: Mapping[str, Any],
    session_count: Optional[int] = None,
    other_feedback: Optional[Union[str, Mapping[str, Any]]] = None,
    *,
    system_prompt: str = learning_path_scheduler_system_prompt,
    task_prompt: str = learning_path_scheduler_task_prompt_reschedule,
) -> JSONDict:
    """Convenience helper to reschedule an existing learning path via the scheduler."""

    learning_path_scheduler = LearningPathScheduler(llm)
    payload_dict = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "session_count": session_count,
        "other_feedback": other_feedback,
    }
    return learning_path_scheduler.reschedule(payload_dict)


def refine_learning_path_with_llm(
    llm: Any,
    learning_path: Sequence[Any],
    feedback: Mapping[str, Any],
    *,
    system_prompt: str = learning_path_scheduler_system_prompt,
    task_prompt: str = learning_path_scheduler_task_prompt_reflexion,
) -> JSONDict:
    """Convenience helper around :meth:`LearningPathScheduler.reflexion`."""

    learning_path_scheduler = LearningPathScheduler(llm)
    payload_dict = {
        "learning_path": learning_path,
        "feedback": feedback,
    }
    return learning_path_scheduler.reflexion(payload_dict)


__all__ = [
    "LearningPathScheduler",
    "LearningPathRefinementPayload",
    "LearningPathReschedulePayload",
    "SessionSchedulePayload",
    "schedule_learning_path_with_llm",
    "refine_learning_path_with_llm",
    "reschedule_learning_path_with_llm",
    "_apply_fslsm_overrides",
]
