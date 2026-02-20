from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple, TypeAlias
from pydantic import BaseModel, Field
from base import BaseAgent
from base.search_rag import SearchRagManager
from ..prompts.skill_gap_identifier import skill_gap_identifier_system_prompt, skill_gap_identifier_task_prompt
from ..schemas import SkillRequirements, SkillGaps, GoalAssessment
from ..tools.goal_assessment_tool import create_goal_assessment_tool
from .skill_requirement_mapper import SkillRequirementMapper
from .learning_goal_refiner import LearningGoalRefiner

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = Dict[str, Any]


class SkillGapPayload(BaseModel):
    """Payload for identifying skill gaps (validated)."""

    learning_goal: str = Field(...)
    learner_information: str = Field(...)
    skill_requirements: Dict[str, Any] = Field(...)


class SkillGapIdentifier(BaseAgent):
    """Agent wrapper for skill requirement discovery and gap identification.

    When a SearchRagManager is provided, the agent gains a goal assessment tool
    to evaluate goal quality after identifying gaps.
    """

    name: str = "SkillGapIdentifier"

    def __init__(
        self,
        model: Any,
        search_rag_manager: Optional[SearchRagManager] = None,
    ) -> None:
        tools = None
        if search_rag_manager is not None:
            assess_tool = create_goal_assessment_tool(search_rag_manager)
            tools = [assess_tool]

        super().__init__(
            model=model,
            system_prompt=skill_gap_identifier_system_prompt,
            tools=tools,
            jsonalize_output=True,
        )

    def identify_skill_gap(
        self,
        input_dict: Mapping[str, Any],
    ) -> JSONDict:
        """Identify knowledge gaps using learner information and expected skills."""
        payload_dict = SkillGapPayload(**input_dict).model_dump()
        task_prompt = skill_gap_identifier_task_prompt
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
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

def identify_skill_gap_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str,
    skill_requirements: Optional[Dict[str, Any]] = None,
    search_rag_manager: Optional[SearchRagManager] = None,
) -> Tuple[JSONDict, JSONDict]:
    """Identify skill gaps with auto-refinement loop.

    If the goal is assessed as vague after the first pass, the system
    auto-refines it once and retries. At most 1 auto-refinement occurs.
    All-mastered goals are never auto-refined.

    Returns:
        Tuple of (skill_gaps dict, effective_requirements dict).
    """
    original_goal = learning_goal
    was_auto_refined = False
    retrieved_sources: List[Dict[str, Any]] = []

    for attempt in range(2):  # max 1 refinement retry
        # Step 1: Map goal to skills (with retrieval if available)
        if not skill_requirements or attempt > 0:
            mapper = SkillRequirementMapper(
                llm, search_rag_manager=search_rag_manager,
                retrieved_docs_sink=retrieved_sources,
            )
            effective_requirements = mapper.map_goal_to_skill({"learning_goal": learning_goal})
        else:
            effective_requirements = skill_requirements

        # Step 2: Identify gaps + assess goal
        identifier = SkillGapIdentifier(llm, search_rag_manager=search_rag_manager)
        skill_gaps = identifier.identify_skill_gap(
            {
                "learning_goal": learning_goal,
                "learner_information": learner_information,
                "skill_requirements": effective_requirements,
            },
        )

        # Step 3: Run goal assessment if tools weren't used by the agent
        # (deterministic fallback — always produce goal_assessment)
        goal_assessment = skill_gaps.get("goal_assessment") or {}
        if not goal_assessment and search_rag_manager is not None:
            assess_fn = create_goal_assessment_tool(search_rag_manager)
            goal_assessment = assess_fn.invoke({
                "learning_goal": learning_goal,
                "skill_gaps": skill_gaps.get("skill_gaps", []),
            })

        # Step 4: Auto-refine if vague (only on first attempt)
        is_vague = goal_assessment.get("is_vague", False) if goal_assessment else False
        all_mastered = goal_assessment.get("all_mastered", False) if goal_assessment else False

        if is_vague and not all_mastered and attempt == 0:
            logger.info(f"Goal assessed as vague, auto-refining: '{learning_goal}'")
            try:
                refiner = LearningGoalRefiner(llm)
                refined_result = refiner.refine_goal({
                    "learning_goal": learning_goal,
                    "learner_information": learner_information,
                })
                refined_goal = refined_result.get("refined_goal", learning_goal)
                if refined_goal.strip().lower() != learning_goal.strip().lower():
                    learning_goal = refined_goal
                    was_auto_refined = True
                    logger.info(f"Goal auto-refined to: '{learning_goal}'")
                    continue  # retry with refined goal
            except Exception as e:
                logger.warning(f"Auto-refinement failed: {e}")

        break  # goal is good enough, or we already refined once

    # Always explicitly set auto-refinement fields to prevent LLM hallucination
    goal_assessment["auto_refined"] = was_auto_refined
    goal_assessment["original_goal"] = original_goal if was_auto_refined else None
    goal_assessment["refined_goal"] = learning_goal if was_auto_refined else None

    # Ensure goal_assessment is included in the result
    skill_gaps["goal_assessment"] = goal_assessment

    # Deduplicate retrieved sources by file_name (or full dict as fallback)
    seen_keys: set = set()
    deduped_sources: List[Dict[str, Any]] = []
    for src in retrieved_sources:
        key = src.get("file_name") or str(sorted(src.items()))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_sources.append(src)
    skill_gaps["retrieved_sources"] = deduped_sources

    return skill_gaps, effective_requirements
