from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict, List, TypeAlias

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts.skill_gap_evaluator import skill_gap_evaluator_system_prompt, skill_gap_evaluator_task_prompt

JSONDict: TypeAlias = Dict[str, Any]


class SkillGapEvaluationPayload(BaseModel):
    """Validated input for the skill gap evaluator."""

    learning_goal: str = Field(...)
    learner_information: str = Field(default="")
    retrieved_context: str = Field(default="")
    skill_requirements: dict = Field(...)
    skill_gaps: dict = Field(...)


class SkillGapEvaluationResult(BaseModel):
    """Output schema for skill gap evaluation."""

    is_acceptable: bool = Field(...)
    issues: List[str] = Field(default_factory=list)
    feedback: str = Field(default="")


class SkillGapEvaluator(BaseAgent):
    """Lightweight agent that critiques identified skill gaps for correctness and completeness."""

    name: str = "SkillGapEvaluator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=skill_gap_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, input_dict: Mapping[str, Any]) -> JSONDict:
        """Evaluate identified skill gaps for quality.

        Args:
            input_dict: Must contain 'learning_goal', 'skill_requirements', 'skill_gaps'.
                        Optionally 'learner_information' and 'retrieved_context'.

        Returns:
            A SkillGapEvaluationResult dict with is_acceptable, issues, and feedback.
        """
        payload = SkillGapEvaluationPayload(**input_dict)
        prompt_vars = {
            "learning_goal": payload.learning_goal,
            "learner_information": payload.learner_information,
            "retrieved_context": payload.retrieved_context,
            "skill_requirements": json.dumps(payload.skill_requirements, indent=2),
            "skill_gaps": json.dumps(payload.skill_gaps, indent=2),
        }
        raw_output = self.invoke(prompt_vars, task_prompt=skill_gap_evaluator_task_prompt)
        validated = SkillGapEvaluationResult.model_validate(raw_output)
        return validated.model_dump()
