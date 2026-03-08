from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple, TypeAlias

from langchain_core.documents import Document

from base.llm_factory import LLMFactory
from base.search_rag import SearchRagManager
from ..agents.bias_auditor import BiasAuditor
from ..agents.goal_context_parser import GoalContextParser
from ..agents.learning_goal_refiner import LearningGoalRefiner
from ..agents.skill_gap_evaluator import SkillGapEvaluator
from ..agents.skill_gap_identifier import SkillGapIdentifier
from ..agents.skill_requirement_mapper import SkillRequirementMapper
from ..utils.formatting import _format_retrieved_docs
from ..utils.retrieval import _retrieve_context_for_goal
from ..utils.sources import _deduplicate_sources

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = Dict[str, Any]


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
    fast_llm = LLMFactory.create(model="gpt-4o-mini", model_provider="openai")

    # ── LOOP 1: Goal Clarification (GoalContextParser ↔ LearningGoalRefiner) ──────
    goal_context: Dict[str, Any] = {}
    retrieved_docs: List[Document] = []
    verified_content_flag = False

    for attempt in range(MAX_GOAL_ITERATIONS):
        goal_context = GoalContextParser(fast_llm).parse({
            "learning_goal": learning_goal,
            "learner_information": learner_information,
        })

        # Only retrieve content when context includes retrievable fields
        verified_content_flag = any(
            goal_context.get(k)
            for k in ("course_code", "lecture_numbers", "content_category", "page_number")
        )

        if verified_content_flag:
            retrieved_docs = _retrieve_context_for_goal(goal_context, search_rag_manager)

        if not goal_context.get("is_vague", False):
            break  # goal is specific — proceed to skill gap identification

        if attempt < MAX_GOAL_ITERATIONS - 1:
            try:
                refined = LearningGoalRefiner(fast_llm).refine_goal({
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

    # Format the retrieved content
    retrieved_context_str = _format_retrieved_docs(retrieved_docs) if verified_content_flag else ""

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
                evaluation = SkillGapEvaluator(fast_llm).evaluate({
                    "learning_goal": learning_goal,
                    "learner_information": learner_information,
                    "coverage_context": retrieved_context_str,
                    "skill_requirements": effective_requirements,
                    "skill_gaps": skill_gaps_result,
                })
                if evaluation.get("is_acceptable", False):
                    break  # result accepted
                evaluator_feedback = evaluation.get("feedback", "")
                issues = evaluation.get("issues", [])
                if issues:
                    logger.info("SkillGapEvaluator issues: %s", " | ".join(str(i) for i in issues))
                if evaluator_feedback:
                    logger.info("SkillGapEvaluator rejected result: %s", evaluator_feedback)
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
    skill_gaps_result["goal_context"] = dict(goal_context)
    skill_gaps_result["retrieved_sources"] = _deduplicate_sources(retrieved_docs)

    # ── BIAS AUDIT ─────────────────────────────────────────────────────────────────
    try:
        bias_result = BiasAuditor(fast_llm).audit_skill_gaps({
            "learner_information": learner_information,
            "skill_gaps": skill_gaps_result,
        })
        skill_gaps_result["bias_audit"] = bias_result
    except Exception as e:
        logger.warning(f"BiasAuditor failed: {e}")
        skill_gaps_result["bias_audit"] = {}

    return skill_gaps_result, effective_requirements
