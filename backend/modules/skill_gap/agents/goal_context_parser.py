from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional, TypeAlias

from pydantic import BaseModel, Field

from base import BaseAgent
from ..prompts.goal_context_parser import goal_context_parser_system_prompt, goal_context_parser_task_prompt

JSONDict: TypeAlias = Dict[str, Any]


class GoalContextPayload(BaseModel):
    """Payload for goal context parsing (validated)."""

    learning_goal: str = Field(...)
    learner_information: str = Field(default="")


class GoalContext(BaseModel):
    """Structured output of the GoalContextParser."""

    course_code: Optional[str] = Field(default=None)
    lecture_number: Optional[int] = Field(default=None)
    content_category: Optional[str] = Field(default=None)
    page_number: Optional[int] = Field(default=None)
    is_vague: bool = Field(default=False)


class GoalContextParser(BaseAgent):
    """Lightweight agent that extracts course metadata and assesses goal vagueness."""

    name: str = "GoalContextParser"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=goal_context_parser_system_prompt,
            jsonalize_output=True,
        )

    def parse(self, input_dict: Mapping[str, Any]) -> JSONDict:
        """Parse a learning goal to extract context metadata and assess vagueness.

        Args:
            input_dict: Must contain 'learning_goal' and optionally 'learner_information'.

        Returns:
            A GoalContext dict with course_code, lecture_number, content_category,
            page_number, and is_vague fields.
        """
        payload_dict = GoalContextPayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=goal_context_parser_task_prompt)
        validated = GoalContext.model_validate(raw_output)
        return validated.model_dump()


def parse_goal_context_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str = "",
) -> JSONDict:
    """Convenience helper to parse goal context with the provided LLM."""
    parser = GoalContextParser(llm)
    return parser.parse({
        "learning_goal": learning_goal,
        "learner_information": learner_information,
    })
