from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.content_generator.schemas import LearnerFeedback
from modules.content_generator.prompts.content_feedback_simulator import (
    learner_feedback_simulator_system_prompt,
    learner_feedback_simulator_task_prompt_content,
)


class LearningContentFeedbackPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_content: Any

    @field_validator("learner_profile", "learning_content")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class LearningContentFeedbackSimulator(BaseAgent):

    name: str = "LearningContentFeedbackSimulator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=learner_feedback_simulator_system_prompt,
            jsonalize_output=True,
        )

    def feedback_content(self, payload: LearningContentFeedbackPayload | Mapping[str, Any] | str) -> dict:
        task_prompt = learner_feedback_simulator_task_prompt_content
        if not isinstance(payload, LearningContentFeedbackPayload):
            payload = LearningContentFeedbackPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=task_prompt)
        validated_output = LearnerFeedback.model_validate(raw_output)
        return validated_output.model_dump()


def simulate_content_feedback_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_content: Any,
) -> dict:
    """Simulate learner feedback on learning content."""
    simulator = LearningContentFeedbackSimulator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_content": learning_content,
    }
    return simulator.feedback_content(payload)
