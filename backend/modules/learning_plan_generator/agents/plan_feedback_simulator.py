from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.learning_plan_generator.schemas import LearnerPlanFeedback
from modules.learning_plan_generator.prompts.plan_feedback import (
    plan_feedback_simulator_system_prompt,
    plan_feedback_simulator_task_prompt,
)


class LearningPathFeedbackPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_path: Any

    @field_validator("learner_profile", "learning_path")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class LearningPlanFeedbackSimulator(BaseAgent):

    name: str = "LearningPlanFeedbackSimulator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=plan_feedback_simulator_system_prompt,
            jsonalize_output=True,
        )

    def feedback_path(self, payload: LearningPathFeedbackPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, LearningPathFeedbackPayload):
            payload = LearningPathFeedbackPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=plan_feedback_simulator_task_prompt)
        validated_output = LearnerPlanFeedback.model_validate(raw_output)
        return validated_output.model_dump()


def simulate_path_feedback_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_path: Any,
) -> dict:
    """Simulate learner feedback on a learning path."""
    simulator = LearningPlanFeedbackSimulator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
    }
    return simulator.feedback_path(payload)
