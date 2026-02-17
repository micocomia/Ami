from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from base.search_rag import SearchRagManager
from ..prompts.skill_requirement_mapper import skill_requirement_mapper_system_prompt, skill_requirement_mapper_task_prompt
from ..schemas import SkillRequirements
from ..tools.course_content_retrieval_tool import create_course_content_retrieval_tool


JSONDict: TypeAlias = Dict[str, Any]

class Goal2SkillPayload(BaseModel):
	"""Payload for mapping a learning goal to required skills (validated)."""

	learning_goal: str = Field(...)


class SkillRequirementMapper(BaseAgent):
	"""Agent wrapper for mapping a goal to required skills.

	When a SearchRagManager is provided, the agent gains a retrieval tool
	to ground skill requirements in verified course content.
	"""

	name: str = "SkillRequirementMapper"

	def __init__(
		self,
		model: Any,
		search_rag_manager: Optional[SearchRagManager] = None,
	) -> None:
		tools = None
		if search_rag_manager is not None:
			retrieve_tool = create_course_content_retrieval_tool(search_rag_manager)
			tools = [retrieve_tool]

		super().__init__(
			model=model,
			system_prompt=skill_requirement_mapper_system_prompt,
			tools=tools,
			jsonalize_output=True,
		)

	def map_goal_to_skill(self, input_dict: Mapping[str, Any]) -> JSONDict:
		payload_dict = Goal2SkillPayload(**input_dict).model_dump()
		task_prompt = skill_requirement_mapper_task_prompt
		raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
		validated = SkillRequirements.model_validate(raw_output)
		return validated.model_dump()


def map_goal_to_skills_with_llm(
	llm: Any,
	learning_goal: str,
	search_rag_manager: Optional[SearchRagManager] = None,
) -> JSONDict:
	mapper = SkillRequirementMapper(llm, search_rag_manager=search_rag_manager)
	return mapper.map_goal_to_skill({"learning_goal": learning_goal})
