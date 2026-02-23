from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple, TypeAlias

from langchain_core.documents import Document
from pydantic import BaseModel, Field

from base import BaseAgent
from base.llm_factory import LLMFactory
from base.search_rag import SearchRagManager
from ..prompts.skill_gap_identifier import skill_gap_identifier_system_prompt, skill_gap_identifier_task_prompt
from ..schemas import SkillGaps
from .bias_auditor import BiasAuditor
from .goal_context_parser import GoalContextParser
from .learning_goal_refiner import LearningGoalRefiner
from .skill_gap_evaluator import SkillGapEvaluator
from .skill_requirement_mapper import SkillRequirementMapper

logger = logging.getLogger(__name__)

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


def _retrieve_context_for_goal(
    goal_context: Dict[str, Any],
    search_rag_manager: Optional[SearchRagManager],
) -> List[Document]:
    """Deterministically retrieve course content using parsed goal context."""
    if search_rag_manager is None or search_rag_manager.verified_content_manager is None:
        return []

    vcm = search_rag_manager.verified_content_manager
    course_code = goal_context.get("course_code")
    lecture_number = goal_context.get("lecture_number")
    content_category = goal_context.get("content_category")
    page_number = goal_context.get("page_number")

    query_parts = [p for p in [
        f"course {course_code}" if course_code else None,
        f"lecture {lecture_number}" if lecture_number else None,
        "content",
    ] if p]
    query = " ".join(query_parts)

    effective_category = content_category or ("Lectures" if lecture_number else None)
    require_lecture = bool(effective_category == "Lectures") if effective_category else bool(lecture_number)
    exclude = ["syllabus.json"] if require_lecture else None

    if hasattr(type(vcm), "retrieve_filtered"):
        return vcm.retrieve_filtered(
            query=query,
            k=8,
            course_code=course_code,
            content_category=effective_category,
            lecture_number=lecture_number,
            page_number=page_number,
            exclude_file_names=exclude,
            require_lecture=require_lecture,
        )
    return vcm.retrieve(query, k=8)


def _format_retrieved_docs(docs: List[Document]) -> str:
    """Format retrieved documents into a string for LLM context."""
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs[:5], 1):
        header = f"[Source {i}: {doc.metadata.get('file_name', 'unknown')}]"
        parts.append(f"{header}\n{doc.page_content[:1000]}")
    return "\n\n".join(parts)


def _deduplicate_sources(docs: List[Document]) -> List[Dict[str, Any]]:
    """Deduplicate retrieved sources by (file_name, lecture_number) key."""
    seen, sources = set(), []
    for doc in docs:
        key = (doc.metadata.get("file_name"), doc.metadata.get("lecture_number"))
        if key not in seen:
            seen.add(key)
            sources.append({
                k: v for k, v in doc.metadata.items()
                if k in ("file_name", "lecture_number", "content_category", "course_code", "page_number")
            })
    return sources


def identify_skill_gap_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: str,
    skill_requirements: Optional[Dict[str, Any]] = None,
    search_rag_manager: Optional[SearchRagManager] = None,
) -> Tuple[JSONDict, JSONDict]:
    """Identify skill gaps using a two-loop reflexion architecture.

    Loop 1 (Goal Clarification): GoalContextParser ↔ LearningGoalRefiner
      Iterates until the goal is specific (is_vague=False) or MAX_GOAL_ITERATIONS reached.
      All goal-related decisions happen here and only here.

    Between loops: SkillRequirementMapper called once with the finalized goal + retrieved context.

    Loop 2 (Skill Gap Reflexion): SkillGapIdentifier ↔ SkillGapEvaluator
      Iterates until the evaluator accepts or MAX_EVAL_ITERATIONS reached.
      Evaluator assesses skill gap quality only — no goal refinement.

    After loops: BiasAuditor runs unconditionally.

    Returns:
        Tuple of (skill_gaps dict, effective_requirements dict).
    """
    MAX_GOAL_ITERATIONS = 2
    MAX_EVAL_ITERATIONS = 2

    original_goal = learning_goal
    was_auto_refined = False
    lightweight_llm = LLMFactory.create(model="gpt-4o-mini", model_provider="openai")

    # ── LOOP 1: Goal Clarification (GoalContextParser ↔ LearningGoalRefiner) ──────
    goal_context: Dict[str, Any] = {}
    retrieved_docs: List[Document] = []

    for attempt in range(MAX_GOAL_ITERATIONS):
        goal_context = GoalContextParser(lightweight_llm).parse({
            "learning_goal": learning_goal,
            "learner_information": learner_information,
        })

        retrieved_docs = _retrieve_context_for_goal(goal_context, search_rag_manager)

        if not goal_context.get("is_vague", False):
            break  # goal is specific — proceed to skill gap identification

        if attempt < MAX_GOAL_ITERATIONS - 1:
            try:
                refined = LearningGoalRefiner(lightweight_llm).refine_goal({
                    "learning_goal": learning_goal,
                    "learner_information": learner_information,
                })
                refined_goal = refined.get("refined_goal", learning_goal)
                if refined_goal.strip().lower() != learning_goal.strip().lower():
                    learning_goal = refined_goal
                    was_auto_refined = True
                    logger.info(f"Goal auto-refined to: '{learning_goal}'")
                else:
                    break  # refiner returned same goal; no further progress possible
            except Exception as e:
                logger.warning(f"Goal refinement failed: {e}")
                break
        # On last attempt: keep current state (goal may still be vague), fall through

    retrieved_context_str = _format_retrieved_docs(retrieved_docs)

    # ── MAP REQUIREMENTS ONCE between loops ────────────────────────────────────────
    if skill_requirements:
        effective_requirements = skill_requirements
    else:
        effective_requirements = SkillRequirementMapper(llm).map_goal_to_skill(
            {"learning_goal": learning_goal},
            retrieved_context=retrieved_context_str,
        )

    # ── LOOP 2: Skill Gap Reflexion (SkillGapIdentifier ↔ SkillGapEvaluator) ──────
    skill_gaps_result: JSONDict = {}
    evaluator_feedback = ""

    for iteration in range(MAX_EVAL_ITERATIONS):
        skill_gaps_result = SkillGapIdentifier(llm).identify_skill_gap(
            {
                "learning_goal": learning_goal,
                "learner_information": learner_information,
                "skill_requirements": effective_requirements,
            },
            retrieved_context=retrieved_context_str,
            evaluator_feedback=evaluator_feedback,
        )

        # Skip evaluator on last iteration to avoid a wasted LLM call
        if iteration < MAX_EVAL_ITERATIONS - 1:
            try:
                evaluation = SkillGapEvaluator(lightweight_llm).evaluate({
                    "learning_goal": learning_goal,
                    "learner_information": learner_information,
                    "retrieved_context": retrieved_context_str,
                    "skill_requirements": effective_requirements,
                    "skill_gaps": skill_gaps_result,
                })
                if evaluation.get("is_acceptable", False):
                    break  # result accepted
                evaluator_feedback = evaluation.get("feedback", "")
                if evaluator_feedback:
                    logger.info(f"SkillGapEvaluator rejected result: {evaluator_feedback[:100]}")
            except Exception as e:
                logger.warning(f"SkillGapEvaluator failed: {e}")
                break

    # ── POST-LOOP ──────────────────────────────────────────────────────────────────
    gaps_list = skill_gaps_result.get("skill_gaps", [])
    all_mastered = bool(gaps_list) and all(not g["is_gap"] for g in gaps_list)

    suggestion = ""
    if goal_context.get("is_vague", False):
        suggestion = (
            "Your goal may be too vague or does not match available course content. "
            "Consider making it more specific (e.g., include a topic area or skill)."
        )
    elif all_mastered:
        suggestion = (
            "You already master all required skills for this goal. "
            "Consider setting a more advanced goal or exploring a different topic."
        )

    skill_gaps_result["goal_assessment"] = {
        "is_vague": goal_context.get("is_vague", False),
        "all_mastered": all_mastered,
        "requires_retrieval": bool(retrieved_docs),
        "suggestion": suggestion,
        "auto_refined": was_auto_refined,
        "original_goal": original_goal if was_auto_refined else None,
        "refined_goal": learning_goal if was_auto_refined else None,
    }
    skill_gaps_result["retrieved_sources"] = _deduplicate_sources(retrieved_docs)

    # ── BIAS AUDIT ─────────────────────────────────────────────────────────────────
    try:
        bias_result = BiasAuditor(lightweight_llm).audit_skill_gaps({
            "learner_information": learner_information,
            "skill_gaps": skill_gaps_result,
        })
        skill_gaps_result["bias_audit"] = bias_result
    except Exception as e:
        logger.warning(f"BiasAuditor failed: {e}")
        skill_gaps_result["bias_audit"] = {}

    return skill_gaps_result, effective_requirements
