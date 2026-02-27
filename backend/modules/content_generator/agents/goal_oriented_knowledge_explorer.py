from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

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


class KnowledgeExplorePayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    session_adaptation_contract: Any = ""

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
        raw_output = self.invoke(payload.model_dump(), task_prompt=goal_oriented_knowledge_explorer_task_prompt)
        validated_output = KnowledgePoints.model_validate(raw_output)
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
    }
    explorer = GoalOrientedKnowledgeExplorer(llm)
    return explorer.explore(input_dict)
