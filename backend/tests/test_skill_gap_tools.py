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
from modules.skill_gap.agents.learning_goal_refiner import refine_learning_goal_with_llm
from modules.skill_gap.agents.skill_gap_evaluator import SkillGapEvaluator, SkillGapEvaluationResult


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
            "lecture_numbers": [4],
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
        assert result["lecture_numbers"] == [4]
        assert result["content_category"] == "Lectures"
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_exercises_goal_extracts_category(self, mock_invoke):
        """Goal referencing exercises → content_category='Exercises'."""
        mock_invoke.return_value = {
            "course_code": "DTI5902",
            "lecture_numbers": [3],
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
        assert result["lecture_numbers"] == [3]
        assert result["content_category"] == "Exercises"
        assert result["is_vague"] is False

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_page_number_extracted(self, mock_invoke):
        """Goal with page number → page_number extracted."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_numbers": [4],
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
            "lecture_numbers": None,
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
            "lecture_numbers": None,
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
            "lecture_numbers": None,
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
            "lecture_numbers": [2],
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({"learning_goal": "lecture 2 of 6.0001", "learner_information": ""})
        # All expected keys present from GoalContext schema
        assert set(result.keys()) == {"course_code", "lecture_numbers", "content_category", "page_number", "is_vague"}

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_range_lecture_numbers_supported(self, mock_invoke):
        """Parser accepts inclusive ranges represented as a list."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_numbers": [1, 2, 3],
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({"learning_goal": "lesson 1 to 3 of 6.0001", "learner_information": ""})
        assert result["lecture_numbers"] == [1, 2, 3]

    @patch("modules.skill_gap.agents.goal_context_parser.GoalContextParser.invoke")
    def test_mixed_lecture_numbers_supported(self, mock_invoke):
        """Parser accepts mixed list/range normalization output."""
        mock_invoke.return_value = {
            "course_code": "6.0001",
            "lecture_numbers": [1, 2, 4, 5],
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }
        llm = MagicMock()
        parser = GoalContextParser(llm)
        result = parser.parse({"learning_goal": "lectures 1-2 and 4,5 of 6.0001", "learner_information": ""})
        assert result["lecture_numbers"] == [1, 2, 4, 5]


# ===================================================================
# TestRetrieveContextForGoal
# ===================================================================

class TestRetrieveContextForGoal:
    def test_returns_empty_list_when_no_manager(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal
        result = _retrieve_context_for_goal({"course_code": "6.0001"}, None)
        assert result == []

    def test_returns_empty_list_when_no_vcm(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal
        mgr = MagicMock()
        mgr.verified_content_manager = None
        result = _retrieve_context_for_goal({"course_code": "6.0001"}, mgr)
        assert result == []

    def test_calls_retrieve_filtered_with_course_and_lecture(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

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
            "lecture_numbers": [4],
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
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()
        vcm.retrieve_filtered = MagicMock(return_value=[])
        mgr.verified_content_manager = vcm

        goal_context = {
            "course_code": "6.0001",
            "lecture_numbers": [4],
            "content_category": "Lectures",
            "page_number": 5,
            "is_vague": False,
        }
        _retrieve_context_for_goal(goal_context, mgr)

        call_kwargs = vcm.retrieve_filtered.call_args.kwargs
        assert call_kwargs["page_number"] == 5

    def test_falls_back_to_retrieve_when_no_retrieve_filtered(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal
        mgr = MagicMock()
        vcm = MagicMock(spec=["retrieve"])  # no retrieve_filtered
        vcm.retrieve.return_value = [_make_doc("content")]
        mgr.verified_content_manager = vcm

        goal_context = {"course_code": "6.0001", "lecture_numbers": None,
                        "content_category": None, "page_number": None, "is_vague": False}
        result = _retrieve_context_for_goal(goal_context, mgr)

        vcm.retrieve.assert_called_once()
        assert len(result) == 1

    def test_broad_goal_strong_syllabus_no_lecture_fallback(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()
        syllabus_docs = [
            _make_doc("6.0001 course overview and key topics in computational thinking", content_category="Syllabus"),
            _make_doc("6.0001 syllabus includes algorithms, recursion, and data abstractions", content_category="Syllabus"),
            _make_doc("6.0001 pacing and topic map across major units", content_category="Syllabus"),
        ]

        def _rf(*args, **kwargs):
            if kwargs.get("content_category") == "Syllabus":
                return syllabus_docs
            return []

        vcm.retrieve_filtered = MagicMock(side_effect=_rf)
        mgr.verified_content_manager = vcm
        goal_context = {
            "course_code": "6.0001",
            "lecture_numbers": None,
            "content_category": None,
            "page_number": None,
            "is_vague": False,
        }

        result = _retrieve_context_for_goal(goal_context, mgr)
        assert len(result) == 3
        assert all((d.metadata or {}).get("content_category") == "Syllabus" for d in result)
        assert vcm.retrieve_filtered.call_count == 1
        assert vcm.retrieve_filtered.call_args.kwargs["content_category"] == "Syllabus"

    def test_broad_goal_weak_syllabus_falls_back_to_lecture_diverse(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()

        syllabus_docs = [
            _make_doc("for information about citing these materials, visit terms of use", content_category="Syllabus"),
            _make_doc("6.0001 brief course outline", content_category="Syllabus"),
        ]
        lecture_docs = [
            _make_doc(
                f"6.0001 lecture {i} topic details and examples",
                content_category="Lectures",
                lecture_number=i,
                file_name=f"Lec_{i}.pdf",
            )
            for i in range(1, 11)
        ]

        def _rf(*args, **kwargs):
            if kwargs.get("content_category") == "Syllabus":
                return syllabus_docs
            if kwargs.get("content_category") == "Lectures":
                return lecture_docs
            return []

        vcm.retrieve_filtered = MagicMock(side_effect=_rf)
        mgr.verified_content_manager = vcm
        goal_context = {
            "course_code": "6.0001",
            "lecture_numbers": None,
            "content_category": None,
            "page_number": None,
            "is_vague": False,
        }

        result = _retrieve_context_for_goal(goal_context, mgr)
        assert len(result) <= 8
        categories = [(d.metadata or {}).get("content_category") for d in result]
        assert "Lectures" in categories

        lecture_nums = [
            (d.metadata or {}).get("lecture_number")
            for d in result
            if (d.metadata or {}).get("content_category") == "Lectures"
        ]
        assert len(set(lecture_nums)) >= 4

        # broad-goal flow should query syllabus first, then lectures on fallback
        assert vcm.retrieve_filtered.call_count == 2
        first = vcm.retrieve_filtered.call_args_list[0].kwargs
        second = vcm.retrieve_filtered.call_args_list[1].kwargs
        assert first["content_category"] == "Syllabus"
        assert second["content_category"] == "Lectures"

    def test_multi_lecture_numbers_calls_filtered_per_lecture(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()

        def _rf(*args, **kwargs):
            ln = kwargs.get("lecture_number")
            return [
                _make_doc(
                    f"lecture {ln} content",
                    content_category="Lectures",
                    lecture_number=ln,
                    file_name=f"Lec_{ln}.pdf",
                )
            ]

        vcm.retrieve_filtered = MagicMock(side_effect=_rf)
        mgr.verified_content_manager = vcm
        goal_context = {
            "course_code": "6.0001",
            "lecture_numbers": [1, 2, 3],
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }

        result = _retrieve_context_for_goal(goal_context, mgr)
        assert len(result) == 3
        assert vcm.retrieve_filtered.call_count == 3
        called_lectures = [c.kwargs.get("lecture_number") for c in vcm.retrieve_filtered.call_args_list]
        assert called_lectures == [1, 2, 3]

    def test_multi_lecture_numbers_cap_at_20(self):
        from modules.skill_gap.utils.retrieval import _retrieve_context_for_goal

        class _StubVCM:
            def retrieve_filtered(self, *args, **kwargs): ...
            def retrieve(self, *args, **kwargs): ...

        mgr = MagicMock()
        vcm = _StubVCM()
        vcm.retrieve_filtered = MagicMock(return_value=[])
        mgr.verified_content_manager = vcm

        goal_context = {
            "course_code": "6.0001",
            "lecture_numbers": list(range(1, 31)),
            "content_category": "Lectures",
            "page_number": None,
            "is_vague": False,
        }

        _retrieve_context_for_goal(goal_context, mgr)
        assert vcm.retrieve_filtered.call_count == 20


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

    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_retrieved_context_is_passed_as_coverage_only_context(self, mock_invoke):
        """Retrieved course content should be labeled as coverage-only, not learner evidence."""
        mock_invoke.return_value = {
            "is_acceptable": True,
            "issues": [],
            "feedback": "",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        evaluator.evaluate({
            "learning_goal": "Learn Python",
            "learner_information": "No coding experience",
            "retrieved_context": "Lecture 3 covers loops and functions.",
            "skill_requirements": {"skill_requirements": [{"name": "Loops", "required_level": "beginner"}]},
            "skill_gaps": {"skill_gaps": []},
        })

        prompt_vars = mock_invoke.call_args.args[0]
        task_prompt = mock_invoke.call_args.kwargs["task_prompt"]
        assert prompt_vars["coverage_context"] == "Lecture 3 covers loops and functions."
        assert "retrieved_context" not in prompt_vars
        assert "coverage only" in task_prompt.lower()
        assert "not learner evidence" in task_prompt.lower()

    @patch("modules.skill_gap.agents.skill_gap_evaluator.SkillGapEvaluator.invoke")
    def test_normalizes_structured_issues_to_strings(self, mock_invoke):
        """Structured issue dicts are normalized to strings before schema validation."""
        mock_invoke.return_value = {
            "is_acceptable": False,
            "issues": [
                {
                    "skill_name": "Python",
                    "observed_level": "unlearned",
                    "expected_level": "beginner",
                    "reason": "Work evidence indicates transferable coding basics.",
                }
            ],
            "feedback": "Revise current_level for Python.",
        }
        llm = MagicMock()
        evaluator = SkillGapEvaluator(llm)
        result = evaluator.evaluate({
            "learning_goal": "Learn Python",
            "learner_information": "",
            "retrieved_context": "",
            "skill_requirements": {"skill_requirements": [{"name": "Python", "required_level": "intermediate"}]},
            "skill_gaps": {"skill_gaps": []},
        })

        assert result["is_acceptable"] is False
        assert isinstance(result["issues"], list)
        assert all(isinstance(issue, str) for issue in result["issues"])
        assert "Skill 'Python'" in result["issues"][0]


# ===================================================================
# TestLearningGoalRefiner helper
# ===================================================================

class TestLearningGoalRefinerHelper:
    @patch("modules.skill_gap.agents.learning_goal_refiner.LearningGoalRefiner")
    def test_returns_refined_goal(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "Learn Python for data analysis with Pandas"}
        llm = MagicMock()

        result = refine_learning_goal_with_llm(llm, "learn python")
        assert result["refined_goal"] == "Learn Python for data analysis with Pandas"

    @patch("modules.skill_gap.agents.learning_goal_refiner.LearningGoalRefiner")
    def test_includes_was_refined_true(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "A different goal"}
        llm = MagicMock()

        result = refine_learning_goal_with_llm(llm, "original goal")
        assert result["refined_goal"] == "A different goal"

    @patch("modules.skill_gap.agents.learning_goal_refiner.LearningGoalRefiner")
    def test_was_refined_false_when_unchanged(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "learn python"}
        llm = MagicMock()

        result = refine_learning_goal_with_llm(llm, "learn python")
        assert result["refined_goal"] == "learn python"

    @patch("modules.skill_gap.agents.learning_goal_refiner.LearningGoalRefiner")
    def test_works_with_empty_learner_information(self, MockRefiner):
        mock_instance = MockRefiner.return_value
        mock_instance.refine_goal.return_value = {"refined_goal": "Learn Python for web dev"}
        llm = MagicMock()

        result = refine_learning_goal_with_llm(llm, "learn python", "")
        assert "refined_goal" in result
