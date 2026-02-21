from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from .prompts import (
    learner_feedback_simulator_system_prompt,
    learner_feedback_simulator_task_prompt_path,
    learner_feedback_simulator_task_prompt_content,
)
from .schemas import LearnerFeedback


class LearningPathFeedbackPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_path: Any


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


class LearningPlanFeedbackSimulator(BaseAgent):

    name: str = "LearningPlanFeedbackSimulator"

    def __init__(self, model):
        super().__init__(model=model, jsonalize_output=True)
        self.system_prompt = learner_feedback_simulator_system_prompt

    def feedback_path(self, payload: LearningPathFeedbackPayload | Mapping[str, Any] | str):
        task_prompt = learner_feedback_simulator_task_prompt_path
        if not isinstance(payload, LearningPathFeedbackPayload):
            payload = LearningPathFeedbackPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=task_prompt)
        validated_output = LearnerFeedback.model_validate(raw_output)
        return validated_output.model_dump()


class LearningContentFeedbackSimulator(BaseAgent):

    name: str = "LearningContentFeedbackSimulator"

    def __init__(self, model):
        super().__init__(model=model, jsonalize_output=True)
        self.system_prompt = learner_feedback_simulator_system_prompt

    def feedback_content(self, payload: LearningContentFeedbackPayload | Mapping[str, Any] | str):
        task_prompt = learner_feedback_simulator_task_prompt_content
        if not isinstance(payload, LearningContentFeedbackPayload):
            payload = LearningContentFeedbackPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=task_prompt)
        validated_output = LearnerFeedback.model_validate(raw_output)
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
