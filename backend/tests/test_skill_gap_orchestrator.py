"""Tests for the skill gap orchestrator (two-loop reflexion architecture).

Tests the identify_skill_gap_with_llm function with mocked agents and helpers.

Run from the repo root:
    python -m pytest backend/tests/test_skill_gap_orchestrator.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


MOCK_SKILL_REQUIREMENTS = {
    "skill_requirements": [
        {"name": "Python Basics", "required_level": "intermediate"},
        {"name": "Data Structures", "required_level": "advanced"},
    ]
}

MOCK_SKILL_GAPS_WITH_GAPS = {
    "skill_gaps": [
        {
            "name": "Python Basics",
            "is_gap": True,
            "required_level": "intermediate",
            "current_level": "beginner",
            "reason": "Limited experience",
            "level_confidence": "medium",
        },
        {
            "name": "Data Structures",
            "is_gap": True,
            "required_level": "advanced",
            "current_level": "beginner",
            "reason": "No formal training",
            "level_confidence": "low",
        },
    ],
    "goal_assessment": None,
}

MOCK_SKILL_GAPS_ALL_MASTERED = {
    "skill_gaps": [
        {
            "name": "Python Basics",
            "is_gap": False,
            "required_level": "intermediate",
            "current_level": "advanced",
            "reason": "5 years experience",
            "level_confidence": "high",
        },
    ],
    "goal_assessment": None,
}

_GOAL_CONTEXT_NOT_VAGUE = {
    "course_code": None,
    "lecture_number": None,
    "content_category": None,
    "page_number": None,
    "is_vague": False,
}
_GOAL_CONTEXT_VAGUE = {**_GOAL_CONTEXT_NOT_VAGUE, "is_vague": True}

_EVAL_ACCEPTED = {"is_acceptable": True, "issues": [], "feedback": ""}
_EVAL_REJECTED = {"is_acceptable": False, "issues": ["Gap too broad"], "feedback": "Be more specific"}


def _make_patches(*targets):
    """Return a list of patch objects for the given import paths."""
    return [patch(t) for t in targets]


# ── Helper to apply standard patches ────────────────────────────────────────
_PATCH_BASE = "modules.skill_gap.orchestrators.skill_gap_pipeline"


class TestLoop1GoalClarification:
    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_vague_goal_refined_in_loop1(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Vague on attempt 0 → refiner called → goal changes → re-parse → not vague → breaks.
        Mapper called once; was_auto_refined=True."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()

        parser_instance = MockParser.return_value
        parser_instance.parse.side_effect = [
            _GOAL_CONTEXT_VAGUE,
            _GOAL_CONTEXT_NOT_VAGUE,
        ]

        mock_retrieve.return_value = []

        refiner_instance = MockRefiner.return_value
        refiner_instance.refine_goal.return_value = {"refined_goal": "Learn Python for data science"}

        mapper_instance = MockMapper.return_value
        mapper_instance.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        identifier_instance = MockIdentifier.return_value
        identifier_instance.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()

        evaluator_instance = MockEvaluator.return_value
        evaluator_instance.evaluate.return_value = _EVAL_ACCEPTED

        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        skill_gaps, reqs = identify_skill_gap_with_llm(llm, "learn python", "CS student")

        # Refiner called once (on attempt 0 after vague assessment)
        refiner_instance.refine_goal.assert_called_once()
        # Parser called twice (original + refined goal)
        assert parser_instance.parse.call_count == 2
        # Mapper called once (between loops)
        assert mapper_instance.map_goal_to_skill.call_count == 1
        # Goal was auto-refined
        assert skill_gaps["goal_assessment"]["auto_refined"] is True
        assert skill_gaps["goal_assessment"]["original_goal"] == "learn python"

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_non_vague_goal_skips_loop1_refinement(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """A clear goal should not trigger refinement — refiner never called."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        MockRefiner.assert_not_called()
        assert MockParser.return_value.parse.call_count == 1

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_loop1_max_iterations_respected(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Always vague, goal always changes — refiner called MAX_GOAL_ITERATIONS-1 times."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        # Always vague across all parse calls
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_VAGUE
        mock_retrieve.return_value = []

        call_count = [0]
        def refine_side_effect(d):
            call_count[0] += 1
            return {"refined_goal": f"refined goal {call_count[0]}"}
        MockRefiner.return_value.refine_goal.side_effect = refine_side_effect

        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        MAX_GOAL_ITERATIONS = 2
        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "learn stuff", "student")

        # Refiner called at most MAX_GOAL_ITERATIONS - 1 times
        assert MockRefiner.return_value.refine_goal.call_count <= MAX_GOAL_ITERATIONS - 1
        # Loop exits and proceeds to Loop 2
        assert MockMapper.return_value.map_goal_to_skill.call_count == 1

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_loop1_refiner_returns_same_goal_breaks(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Vague but refiner returns same goal — breaks immediately; refiner called once."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_VAGUE
        mock_retrieve.return_value = []
        MockRefiner.return_value.refine_goal.return_value = {"refined_goal": "learn stuff"}
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "learn stuff", "student")

        MockRefiner.return_value.refine_goal.assert_called_once()
        # Goal was NOT auto-refined (same goal returned)
        assert skill_gaps["goal_assessment"]["auto_refined"] is False


class TestLoop2SkillGapReflexion:
    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_evaluator_accepts_on_first_pass(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Evaluator accepts immediately — identifier called once."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        assert MockIdentifier.return_value.identify_skill_gap.call_count == 1
        MockEvaluator.return_value.evaluate.assert_called_once()

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_evaluator_rejects_then_accepts(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Evaluator rejects iteration 0 with feedback, accepts iteration 1.
        Identifier called twice; second call receives evaluator_feedback."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.side_effect = [_EVAL_REJECTED, _EVAL_ACCEPTED]
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        assert MockIdentifier.return_value.identify_skill_gap.call_count == 2
        # Second identifier call should have received the feedback
        second_call_kwargs = MockIdentifier.return_value.identify_skill_gap.call_args_list[1]
        assert second_call_kwargs.kwargs.get("evaluator_feedback") == _EVAL_REJECTED["feedback"]

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_evaluator_max_iterations_respected(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Evaluator always rejects — loop exits after MAX_EVAL_ITERATIONS; identifier called that many times."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_REJECTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        MAX_EVAL_ITERATIONS = 2
        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        assert MockIdentifier.return_value.identify_skill_gap.call_count == MAX_EVAL_ITERATIONS
        # Evaluator called MAX_EVAL_ITERATIONS - 1 times (skipped on last iteration)
        assert MockEvaluator.return_value.evaluate.call_count == MAX_EVAL_ITERATIONS - 1


class TestPostLoop:
    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_bias_audit_always_runs(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """BiasAuditor runs unconditionally and result is in skill_gaps."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        bias_output = {"bias_flags": [], "overall_bias_risk": "low"}
        MockBias.return_value.audit_skill_gaps.return_value = bias_output

        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        MockBias.return_value.audit_skill_gaps.assert_called_once()
        assert skill_gaps["bias_audit"] == bias_output

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_all_mastered_in_goal_assessment(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """All is_gap=False → goal_assessment.all_mastered=True."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_ALL_MASTERED.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "Learn Python", "Expert Python programmer")

        assert skill_gaps["goal_assessment"]["all_mastered"] is True
        assert "master" in skill_gaps["goal_assessment"]["suggestion"].lower()

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_goal_assessment_always_present(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """goal_assessment is always present in the response."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        MockEvaluator.return_value.evaluate.return_value = _EVAL_ACCEPTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        skill_gaps, _ = identify_skill_gap_with_llm(llm, "Learn Python", "CS student", search_rag_manager=None)

        assert "goal_assessment" in skill_gaps
        assert isinstance(skill_gaps["goal_assessment"], dict)
        assert "goal_context" in skill_gaps
        assert skill_gaps["goal_context"] == _GOAL_CONTEXT_NOT_VAGUE

    @patch(f"{_PATCH_BASE}.LLMFactory")
    @patch(f"{_PATCH_BASE}.BiasAuditor")
    @patch(f"{_PATCH_BASE}.SkillGapEvaluator")
    @patch(f"{_PATCH_BASE}.SkillRequirementMapper")
    @patch(f"{_PATCH_BASE}.SkillGapIdentifier")
    @patch(f"{_PATCH_BASE}.LearningGoalRefiner")
    @patch(f"{_PATCH_BASE}._retrieve_context_for_goal")
    @patch(f"{_PATCH_BASE}.GoalContextParser")
    def test_loop2_no_goal_refinement(
        self,
        MockParser, mock_retrieve, MockRefiner, MockIdentifier,
        MockMapper, MockEvaluator, MockBias, MockLLMFactory,
    ):
        """Loop 2 must never trigger goal refinement — LearningGoalRefiner not called in Loop 2."""
        from modules.skill_gap.orchestrators.skill_gap_pipeline import identify_skill_gap_with_llm

        MockLLMFactory.create.return_value = MagicMock()
        MockParser.return_value.parse.return_value = _GOAL_CONTEXT_NOT_VAGUE
        mock_retrieve.return_value = []
        MockMapper.return_value.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS
        MockIdentifier.return_value.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()
        # Evaluator always rejects
        MockEvaluator.return_value.evaluate.return_value = _EVAL_REJECTED
        MockBias.return_value.audit_skill_gaps.return_value = {}

        llm = MagicMock()
        identify_skill_gap_with_llm(llm, "Learn Python for data science", "CS student")

        # Refiner was never called (goal was not vague, and Loop 2 never calls refiner)
        MockRefiner.assert_not_called()
