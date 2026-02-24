from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Dict, TypeAlias

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts.skill_gap_identifier import skill_gap_identifier_system_prompt, skill_gap_identifier_task_prompt
from ..schemas import SkillGaps

JSONDict: TypeAlias = Dict[str, Any]


class SkillGapPayload(BaseModel):
    """Payload for identifying skill gaps (validated)."""

    learning_goal: str = Field(...)
    learner_information: str = Field(...)
    skill_requirements: Dict[str, Any] = Field(...)
    retrieved_context: str = Field(default="")
    evaluator_feedback: str = Field(default="")


class SkillGapIdentifier(BaseAgent):
    """Agent that identifies skill gaps between a learner profile and a learning goal."""

    name: str = "SkillGapIdentifier"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=skill_gap_identifier_system_prompt,
            tools=None,
            jsonalize_output=True,
        )

    def identify_skill_gap(
        self,
        input_dict: Mapping[str, Any],
        retrieved_context: str = "",
        evaluator_feedback: str = "",
    ) -> JSONDict:
        """Identify knowledge gaps using learner information and expected skills."""
        payload = SkillGapPayload(
            **input_dict,
            retrieved_context=retrieved_context,
            evaluator_feedback=evaluator_feedback,
        )
        prompt_vars = payload.model_dump()
        prompt_vars["skill_requirements"] = json.dumps(payload.skill_requirements, indent=2)
        raw_output = self.invoke(prompt_vars, task_prompt=skill_gap_identifier_task_prompt)
        normalized_output = self._normalize_is_gap_flags(raw_output)
        validated = SkillGaps.model_validate(normalized_output)
        return validated.model_dump()

    @staticmethod
    def _normalize_is_gap_flags(raw_output: Any) -> Any:
        """Derive is_gap from levels to prevent contradictory LLM outputs."""
        if not isinstance(raw_output, dict):
            return raw_output

        skill_gaps = raw_output.get("skill_gaps")
        if not isinstance(skill_gaps, list):
            return raw_output

        order = {
            "unlearned": 0,
            "beginner": 1,
            "intermediate": 2,
            "advanced": 3,
            "expert": 4,
        }

        for gap in skill_gaps:
            if not isinstance(gap, dict):
                continue
            required = str(gap.get("required_level", "")).strip().lower()
            current = str(gap.get("current_level", "")).strip().lower()
            if required in order and current in order:
                gap["is_gap"] = order[current] < order[required]

        return raw_output
