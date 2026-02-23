"""Tests for skill gap agents and helpers: GoalContextParser, _retrieve_context_for_goal,
SkillGapEvaluator, and LearningGoalRefiner (unchanged).

All LLM calls are mocked. Tests verify agent contracts and helper logic.

Run from the repo root:
    python -m pytest backend/tests/test_skill_gap_tools.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from langchain_core.documents import Document

from modules.skill_gap.agents.goal_context_parser import GoalContextParser, GoalContext
from modules.skill_gap.agents.skill_gap_evaluator import SkillGapEvaluator, SkillGapEvaluationResult
from modules.skill_gap.tools.goal_refinement_tool import create_goal_refinement_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(content, **metadata):
    return Document(page_content=content, metadata=metadata)


def _mock_llm_with_output(output: dict):
    """Return a mock LLM whose invoke() side-effect satisfies BaseAgent.invoke()."""
    llm = MagicMock()
    return llm


def _make_goal_context_parser_with_output(output: dict):
    """Return a GoalContextParser whose .parse() returns `output` directly (LLM mocked)."""
    parser = MagicMock(spec=GoalContextParser)
    parser.parse.return_value = output
    return parser


# ===================================================================
# TestGoalContextParser
# ===================================================================

class TestGoalContextParser:
    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_course_specific_goal_not_vague(self, mock_invoke):
        """Goal with course code → is_vague=False, course_code extracted."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_number": 4,
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "learn about Week 4 of 6.0001",
            "learner_information": "",
        })
        assert result["course_code"] == "6.0001"
        assert result["lecture_number"] == 4
        assert result["content_category"] == "Lectures"
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_exercises_goal_extracts_category(self, mock_invoke):
        """Goal referencing exercises → content_category='Exercises'."""
        mock_invoke.return_value = {
            "course_code": "DTI5902",
            "lecture_number": 3,
            "content_category": "Exercises",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "Show me the exercises from Lesson 3 of DTI5902",
            "learner_information": "",
        })
        assert result["course_code"] == "DTI5902"
        assert result["lecture_number"] == 3
        assert result["content_category"] == "Exercises"
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_page_number_extracted(self, mock_invoke):
        """Goal with page number → page_number extracted."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_number": 4,
            "content_category": "Lectures",
            "page_number": 5,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "What is on page 5 of lecture 4 of 6.0001?",
            "learner_information": "",
        })
        assert result["page_number"] == 5
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_generic_goal_is_vague(self, mock_invoke):
        """Generic goal → is_vague=True, all fields null."""
        mock_invoke.return_value = {
            "course_code": None,
            "lecture_number": None,
            "content_category": None,
            "page_number": None,
            "is_vague": True,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "I want to learn HR stuff",
            "learner_information": "",
        })
        assert result["is_vague"] is True
        assert result["course_code"] is None

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_learn_python_with_tech_background_is_vague(self, mock_invoke):
        """'learn Python' with tech background → is_vague=True."""
        mock_invoke.return_value = {
            "course_code": None,
            "lecture_number": None,
            "content_category": None,
            "page_number": None,
            "is_vague": True,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "learn Python",
            "learner_information": "Senior ML engineer with 10 years of Python experience",
        })
        assert result["is_vague"] is True

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_specific_domain_goal_not_vague(self, mock_invoke):
        """'learn Python for data analysis' → is_vague=False."""
        mock_invoke.return_value = {
            "course_code": None,
            "lecture_number": None,
            "content_category": None,
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({
            "learning_goal": "learn Python for data analysis",
            "learner_information": "",
        })
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_output_validated_against_schema(self, mock_invoke):
        """Parser validates output through GoalContext schema."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_number": 2,
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({"learning_goal": "lecture 2 of 6.0001", "learner_information": ""})
        # All expected keys present from GoalContext schema
        assert set(result.keys()) == {"course_code", "lecture_number", "content_category", "page_number", "is_vague"}


# ===================================================================
# TestRetrieveContextForGoal
# ===================================================================

class TestRetrieveContextForGoal:
    def test_returns_empty_list_when_no_manager(self):
        from modules.skill_gap.agents.skill_gap_identifier import _retrieve_context_for_goal
        result = _retrieve_context_for_goal({"course_code": "6.0001"}, None)
        assert result == []

    def test_returns_empty_list_when_no_vcm(self):
        from modules.skill_gap.agents.skill_gap_identifier import _retrieve_context_for_goal
        mgr = MagicMock()
        mgr.verified_content_manager = None
        result = _retrieve_context_for_goal({"course_code": "6.0001"}, mgr)
        assert result == []

    def test_calls_retrieve_filtered_with_course_and_lecture(self):
        from modules.skill_gap.agents.skill_gap_identifier import _retrieve_context_for_goal

        # Use a stub class so hasattr(type(vcm), "retrieve_filtered") returns True
        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()
        vcm.retrieve_filtered = MagicMock(return_value=[_make_doc("content")])
        mgr.verified_content_manager = vcm

        goal_context = {
            "course_code": "6.0001",
            "lecture_number": 4,
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        result = _retrieve_context_for_goal(goal_context, mgr)

        vcm.retrieve_filtered.assert_called_once()
        call_kwargs = vcm.retrieve_filtered.call_args.kwargs
        assert call_kwargs["course_code"] == "6.0001"
        assert call_kwargs["lecture_number"] == 4
        assert call_kwargs["content_category"] == "Lectures"
        assert len(result) == 1

    def test_passes_page_number_to_retrieve_filtered(self):
        from modules.skill_gap.agents.skill_gap_identifier import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()
        vcm.retrieve_filtered = MagicMock(return_value=[])
        mgr.verified_content_manager = vcm

        goal_context = {
            "course_code": "6.0001",
            "lecture_number": 4,
            "content_category": "Lectures",
            "page_number": 5,
            "is_vague": False,
        }
        _retrieve_context_for_goal(goal_context, mgr)

        call_kwargs = vcm.retrieve_filtered.call_args.kwargs
        assert call_kwargs["page_number"] == 5

    def test_falls_back_to_retrieve_when_no_retrieve_filtered(self):
        from modules.skill_gap.agents.skill_gap_identifier import _retrieve_context_for_goal
        mgr = MagicMock()
        vcm = MagicMock(spec=["retrieve"])  # no retrieve_filtered
        vcm.retrieve.return_value = [_make_doc("content")]
        mgr.verified_content_manager = vcm

        goal_context = {"course_code": "6.0001", "lecture_number": None,
                        "content_category": None, "page_number": None, "is_vague": False}
        result = _retrieve_context_for_goal(goal_context, mgr)

        vcm.retrieve.assert_called_once()
        assert len(result) == 1


# ===================================================================
# TestSkillGapEvaluator
# ===================================================================

class TestSkillGapEvaluator:
    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_returns_is_acceptable_true(self, mock_invoke):
        """Evaluator returns is_acceptable=True when gaps are correct."""
        mock_invoke.return_value = {
            "is_acceptable": True,
            "issues": [],
            "feedback": "",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        result = evaluator.evaluate({
            "learning_goal": "Learn Python for data science",
            "learner_information": "CS student",
            "retrieved_context": "",
            "skill_requirements": {"skill_requirements": [{"name": "Python", "required_level": "intermediate"}]},
            "skill_gaps": {"skill_gaps": [{"name": "Python", "is_gap": True, "required_level": "intermediate",
                                           "current_level": "beginner", "reason": "No experience",
                                           "level_confidence": "medium"}]},
        })
        assert result["is_acceptable"] is True
        assert result["issues"] == []

    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_returns_feedback_on_rejection(self, mock_invoke):
        """Evaluator returns feedback when gaps are not acceptable."""
        mock_invoke.return_value = {
            "is_acceptable": False,
            "issues": ["Python Basics marked expert with low confidence"],
            "feedback": "Revise the current_level for Python Basics",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        result = evaluator.evaluate({
            "learning_goal": "Learn Python",
            "learner_information": "Beginner with no experience",
            "retrieved_context": "",
            "skill_requirements": {"skill_requirements": [{"name": "Python Basics", "required_level": "intermediate"}]},
            "skill_gaps": {"skill_gaps": [{"name": "Python Basics", "is_gap": False, "required_level": "intermediate",
                                           "current_level": "expert", "reason": "Unknown",
                                           "level_confidence": "low"}]},
        })
        assert result["is_acceptable"] is False
        assert "Revise" in result["feedback"]
        assert len(result["issues"]) > 0

    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_no_needs_goal_refinement_field(self, mock_invoke):
        """Evaluator result must NOT include needs_goal_refinement — goal is Loop 1's responsibility."""
        mock_invoke.return_value = {
            "is_acceptable": True,
            "issues": [],
            "feedback": "",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        result = evaluator.evaluate({
            "learning_goal": "Learn Python",
            "learner_information": "",
            "retrieved_context": "",
            "skill_requirements": {"skill_requirements": []},
            "skill_gaps": {"skill_gaps": []},
        })
        assert "needs_goal_refinement" not in result

    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_schema_validates_output(self, mock_invoke):
        """Result is validated against SkillGapEvaluationResult schema."""
        mock_invoke.return_value = {
            "is_acceptable": False,
            "issues": ["Missing skill coverage"],
            "feedback": "Add recursion gap",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        result = evaluator.evaluate({
            "learning_goal": "Learn Python",
            "learner_information": "",
            "retrieved_context": "lecture content about recursion",
            "skill_requirements": {"skill_requirements": [{"name": "Recursion", "required_level": "intermediate"}]},
            "skill_gaps": {"skill_gaps": []},
        })
        # All SkillGapEvaluationResult fields present
        assert "is_acceptable" in result
        assert "issues" in result
        assert "feedback" in result


# ===================================================================
# TestGoalRefinementTool (unchanged)
# ===================================================================

class TestGoalRefinementTool:
    @patch("modules.skill_gap.tools.goal_refinement_tool.LearningGoalRefiner")
    def test_returns_refined_goal(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "Learn Python for data analysis with Pandas"}
        llm = MagicMock()

        tool = create_goal_refinement_tool(llm)
        result = tool.invoke({"learning_goal": "learn python"})
        assert result["refined_goal"] == "Learn Python for data analysis with Pandas"
        assert result["was_refined"] is True

    @patch("modules.skill_gap.tools.goal_refinement_tool.LearningGoalRefiner")
    def test_includes_was_refined_true(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "A different goal"}
        llm = MagicMock()

        tool = create_goal_refinement_tool(llm)
        result = tool.invoke({"learning_goal": "original goal"})
        assert result["was_refined"] is True

    @patch("modules.skill_gap.tools.goal_refinement_tool.LearningGoalRefiner")
    def test_was_refined_false_when_unchanged(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "learn python"}
        llm = MagicMock()

        tool = create_goal_refinement_tool(llm)
        result = tool.invoke({"learning_goal": "learn python"})
        assert result["was_refined"] is False

    @patch("modules.skill_gap.tools.goal_refinement_tool.LearningGoalRefiner")
    def test_works_with_empty_learner_information(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "Learn Python for web dev"}
        llm = MagicMock()

        tool = create_goal_refinement_tool(llm)
        result = tool.invoke({"learning_goal": "learn python", "learner_information": ""})
        assert "refined_goal" in result
