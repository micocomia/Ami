from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.content_generator.prompts.integrated_document_evaluator import (
    integrated_document_evaluator_system_prompt,
    integrated_document_evaluator_task_prompt,
)
from modules.content_generator.schemas import IntegratedDocumentEvaluation


class IntegratedDocumentEvaluationPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_session: Any = Field(default_factory=dict)
    knowledge_points: Any = Field(default_factory=list)
    session_adaptation_contract: Any = ""
    document: str = ""

    @field_validator(
        "learner_profile",
        "learning_session",
        "knowledge_points",
        "session_adaptation_contract",
    )
    @classmethod
    def coerce_jsonish(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            return value.strip()
        return value


class IntegratedDocumentEvaluator(BaseAgent):
    name: str = "IntegratedDocumentEvaluator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=integrated_document_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, payload: IntegratedDocumentEvaluationPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, IntegratedDocumentEvaluationPayload):
            payload = IntegratedDocumentEvaluationPayload.model_validate(payload)
        raw_output = self.invoke(
            payload.model_dump(),
            task_prompt=integrated_document_evaluator_task_prompt,
        )
        validated_output = IntegratedDocumentEvaluation.model_validate(raw_output)
        return validated_output.model_dump()


def evaluate_integrated_document_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_session: Mapping[str, Any],
    knowledge_points: list[dict[str, Any]],
    session_adaptation_contract: Any,
    document: str,
) -> dict:
    evaluator = IntegratedDocumentEvaluator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_session": learning_session,
        "knowledge_points": knowledge_points,
        "session_adaptation_contract": session_adaptation_contract,
        "document": document,
    }
    return evaluator.evaluate(payload)
