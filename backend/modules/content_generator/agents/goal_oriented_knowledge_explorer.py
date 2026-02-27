from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from pydantic import BaseModel, field_validator, ValidationError

from base import BaseAgent
from modules.content_generator.prompts.goal_oriented_knowledge_explorer import (
    goal_oriented_knowledge_explorer_system_prompt,
    goal_oriented_knowledge_explorer_task_prompt,
)
from modules.content_generator.schemas import KnowledgePoints
from modules.content_generator.utils import (
    build_session_adaptation_contract,
    format_session_adaptation_contract,
)

logger = logging.getLogger(__name__)


def _coerce_knowledge_points_output(raw_output: Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(raw_output, list):
        knowledge_points = raw_output
    elif isinstance(raw_output, dict):
        knowledge_points = raw_output.get("knowledge_points", [])
    else:
        knowledge_points = []

    if not isinstance(knowledge_points, list):
        knowledge_points = []

    normalized_items: list[dict[str, Any]] = []
    for item in knowledge_points:
        if not isinstance(item, dict):
            continue
        normalized_items.append(item)
    return {"knowledge_points": normalized_items}


class KnowledgeExplorePayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    session_adaptation_contract: Any = ""
    schema_repair_feedback: str = ""

    @field_validator("learner_profile", "learning_path", "learning_session", "session_adaptation_contract")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v

class GoalOrientedKnowledgeExplorer(BaseAgent):
    name: str = "GoalOrientedKnowledgeExplorer"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=goal_oriented_knowledge_explorer_system_prompt, jsonalize_output=True)

    def explore(self, payload: KnowledgeExplorePayload | Mapping[str, Any] | str | dict):
        if not isinstance(payload, KnowledgeExplorePayload):
            payload = KnowledgeExplorePayload.model_validate(payload)

        first_payload = payload.model_dump()
        raw_output = self.invoke(first_payload, task_prompt=goal_oriented_knowledge_explorer_task_prompt)
        coerced_output = _coerce_knowledge_points_output(raw_output)
        try:
            validated_output = KnowledgePoints.model_validate(coerced_output)
            return validated_output.model_dump()
        except ValidationError as exc:
            errors_json = json.dumps(exc.errors(), ensure_ascii=True)
            logger.warning("Knowledge explorer schema mismatch, issuing one repair retry: %s", errors_json)

        retry_payload = payload.model_dump()
        retry_payload["schema_repair_feedback"] = (
            "Your previous output failed schema validation. "
            "Fix every error and return only valid JSON matching the exact schema.\n"
            f"Validation errors: {errors_json}"
        )
        repaired_output = self.invoke(retry_payload, task_prompt=goal_oriented_knowledge_explorer_task_prompt)
        validated_output = KnowledgePoints.model_validate(_coerce_knowledge_points_output(repaired_output))
        return validated_output.model_dump()


def explore_knowledge_points_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    *,
    session_adaptation_contract: Mapping[str, Any] | None = None,
):
    """Convenience wrapper to explore knowledge points for a session using the agent.

    Mirrors the selected helper signature and behavior.
    """
    if session_adaptation_contract is None:
        session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
    input_dict = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
        "session_adaptation_contract": format_session_adaptation_contract(session_adaptation_contract),
        "schema_repair_feedback": "",
    }
    explorer = GoalOrientedKnowledgeExplorer(llm)
    return explorer.explore(input_dict)
