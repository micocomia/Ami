from typing import Any, Dict, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, Field

from base import BaseAgent
from modules.learning_plan_generator.schemas import LearningPath
from modules.learning_plan_generator.prompts.learning_path_scheduling import (
    learning_path_scheduler_system_prompt,
    learning_path_scheduler_task_prompt_reflexion,
    learning_path_scheduler_task_prompt_reschedule,
    learning_path_scheduler_task_prompt_session,
)


JSONDict = Dict[str, Any]
_FSLSM_MODERATE = 0.3
_FSLSM_STRONG = 0.7


def _get_fslsm_dim(learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]], dim_name: str) -> float:
    """Best-effort extraction of a single FSLSM dimension from a learner profile."""
    if not isinstance(learner_profile, Mapping):
        return 0.0
    try:
        dims = (
            learner_profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        if not isinstance(dims, Mapping):
            return 0.0
        value = dims.get(dim_name, 0.0)
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def apply_fslsm_structural_overrides(
    learning_path: Sequence[Any],
    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]],
    *,
    preserve_learned: bool = False,
) -> list[dict[str, Any]]:
    """Deterministically align structural session fields with FSLSM values."""
    processing = _get_fslsm_dim(learner_profile, "fslsm_processing")
    perception = _get_fslsm_dim(learner_profile, "fslsm_perception")
    understanding = _get_fslsm_dim(learner_profile, "fslsm_understanding")

    base_updates = {
        "has_checkpoint_challenges": False,
        "thinking_time_buffer_minutes": 0,
        "session_sequence_hint": None,
        "navigation_mode": "linear",
    }

    if processing <= -_FSLSM_MODERATE:
        base_updates["has_checkpoint_challenges"] = True
    elif processing >= _FSLSM_STRONG:
        base_updates["thinking_time_buffer_minutes"] = 10
    elif processing >= _FSLSM_MODERATE:
        base_updates["thinking_time_buffer_minutes"] = 5

    if perception <= -_FSLSM_MODERATE:
        base_updates["session_sequence_hint"] = "application-first"
    elif perception >= _FSLSM_MODERATE:
        base_updates["session_sequence_hint"] = "theory-first"

    if understanding >= _FSLSM_MODERATE:
        base_updates["navigation_mode"] = "free"

    normalized_sessions: list[dict[str, Any]] = []
    for session in learning_path:
        session_dict = dict(session) if isinstance(session, Mapping) else {}
        if preserve_learned and session_dict.get("if_learned", False):
            normalized_sessions.append(session_dict)
            continue
        normalized_sessions.append({**session_dict, **base_updates})
    return normalized_sessions


class SessionSchedulePayload(BaseModel):
    """Input payload for scheduling sessions (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    session_count: int = 0
    goal_context: Optional[Mapping[str, Any]] = None


class LearningPathRefinementPayload(BaseModel):
    """Input payload for reflexion/refinement of a learning path (validated)."""

    learning_path: Sequence[Any]
    feedback: Union[str, Dict[str, Any], Mapping[str, Any]]
    evaluator_feedback: str = Field(default="")
    goal_context: Optional[Mapping[str, Any]] = None


class LearningPathReschedulePayload(BaseModel):
    """Input payload for rescheduling an existing learning path (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    learning_path: Sequence[Any]
    session_count: Optional[Union[int, str]] = None
    other_feedback: Optional[Union[str, Dict[str, Any], Mapping[str, Any]]] = None
    goal_context: Optional[Mapping[str, Any]] = None


class LearningPathScheduler(BaseAgent):
    """High-level agent orchestrating learning path scheduling tasks."""

    name: str = "LearningPathScheduler"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=learning_path_scheduler_system_prompt,
            tools=None,
            jsonalize_output=True,
        )

    def schedule_session(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Schedule sessions based on learner profile and desired count."""
        payload_dict = SessionSchedulePayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_session
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearningPath.model_validate(raw_output)
        result = validated_output.model_dump()
        result["learning_path"] = apply_fslsm_structural_overrides(
            result.get("learning_path", []),
            payload_dict["learner_profile"],
        )
        return result

    def reflexion(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Refine the learning path based on evaluator feedback."""
        payload_dict = LearningPathRefinementPayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_reflexion
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated = LearningPath.model_validate(raw_output)
        result = validated.model_dump()
        learner_profile = {}
        feedback = payload_dict.get("feedback")
        if isinstance(feedback, Mapping):
            learner_profile = feedback.get("learner_profile", {}) or {}
        result["learning_path"] = apply_fslsm_structural_overrides(
            result.get("learning_path", []),
            learner_profile,
            preserve_learned=True,
        )
        return result

    def reschedule(self, input_dict: Dict[str, Any]) -> JSONDict:
        """Reschedule the learning path with optional new session_count/feedback."""
        payload_dict = LearningPathReschedulePayload(**input_dict).model_dump()
        task_prompt = learning_path_scheduler_task_prompt_reschedule
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated = LearningPath.model_validate(raw_output)
        result = validated.model_dump()
        result["learning_path"] = apply_fslsm_structural_overrides(
            result.get("learning_path", []),
            payload_dict["learner_profile"],
            preserve_learned=True,
        )
        return result


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def schedule_learning_path_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    session_count: int = 0,
    goal_context: Optional[Mapping[str, Any]] = None,
) -> JSONDict:
    """Convenience helper to create a scheduler and produce a new learning path."""
    learning_path_scheduler = LearningPathScheduler(llm)
    payload_dict = {
        "learner_profile": learner_profile,
        "session_count": session_count,
        "goal_context": goal_context,
    }
    return learning_path_scheduler.schedule_session(payload_dict)


def reschedule_learning_path_with_llm(
    llm: Any,
    learning_path: Sequence[Any],
    learner_profile: Mapping[str, Any],
    session_count: Optional[int] = None,
    other_feedback: Optional[Union[str, Mapping[str, Any]]] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
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
        "goal_context": goal_context,
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
    "apply_fslsm_structural_overrides",
    "schedule_learning_path_with_llm",
    "refine_learning_path_with_llm",
    "reschedule_learning_path_with_llm",
]
