"""Tests for skill gap tools: course content retrieval, goal assessment, goal refinement.

All LLM calls are mocked. Tests verify tool contracts and filtering logic.

Run from the repo root:
    python -m pytest backend/tests/test_skill_gap_tools.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from langchain_core.documents import Document

from modules.skill_gap.tools.course_content_retrieval_tool import create_course_content_retrieval_tool
from modules.skill_gap.tools.goal_assessment_tool import create_goal_assessment_tool
from modules.skill_gap.tools.goal_refinement_tool import create_goal_refinement_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(content, **metadata):
    return Document(page_content=content, metadata=metadata)


def _mock_search_rag_manager(docs=None):
    """Return a mock SearchRagManager with a VerifiedContentManager that returns `docs`."""
    mgr = MagicMock()
    vcm = MagicMock()
    vcm.retrieve.return_value = docs if docs is not None else []
    mgr.verified_content_manager = vcm
    return mgr


# ===================================================================
# TestCourseContentRetrievalTool
# ===================================================================

class TestCourseContentRetrievalTool:
    def test_returns_formatted_docs(self):
        docs = [
            _make_doc("Intro to Python", title="Syllabus", source_type="verified_content", content_category="Syllabus"),
        ]
        mgr = _mock_search_rag_manager(docs)
        tool = create_course_content_retrieval_tool(mgr)
        result = tool.invoke({"query": "python basics"})
        assert "Intro to Python" in result

    def test_filters_by_content_category(self):
        docs = [
            _make_doc("Syllabus content", content_category="Syllabus"),
            _make_doc("Lecture content", content_category="Lectures"),
        ]
        mgr = _mock_search_rag_manager(docs)
        tool = create_course_content_retrieval_tool(mgr)
        result = tool.invoke({"query": "python", "content_category": "Syllabus"})
        assert "Syllabus content" in result
        assert "Lecture content" not in result

    def test_filters_by_lecture_number(self):
        docs = [
            _make_doc("Lecture 1 content", content_category="Lectures", lecture_number=1),
            _make_doc("Lecture 3 content", content_category="Lectures", lecture_number=3),
        ]
        mgr = _mock_search_rag_manager(docs)
        tool = create_course_content_retrieval_tool(mgr)
        result = tool.invoke({"query": "loops", "lecture_number": 3})
        assert "Lecture 3 content" in result
        assert "Lecture 1 content" not in result

    def test_no_results_returns_message(self):
        mgr = _mock_search_rag_manager([])
        tool = create_course_content_retrieval_tool(mgr)
        result = tool.invoke({"query": "quantum physics"})
        assert "No results found" in result

    def test_no_vcm_returns_fallback_message(self):
        tool = create_course_content_retrieval_tool(None)
        result = tool.invoke({"query": "anything"})
        assert "No verified course content available" in result

    def test_combined_filtering(self):
        docs = [
            _make_doc("Lec 2 syllabus", content_category="Syllabus", lecture_number=2),
            _make_doc("Lec 2 lecture", content_category="Lectures", lecture_number=2),
            _make_doc("Lec 3 lecture", content_category="Lectures", lecture_number=3),
        ]
        mgr = _mock_search_rag_manager(docs)
        tool = create_course_content_retrieval_tool(mgr)
        result = tool.invoke({"query": "topic", "content_category": "Lectures", "lecture_number": 2})
        assert "Lec 2 lecture" in result
        assert "Lec 3 lecture" not in result
        assert "Lec 2 syllabus" not in result


# ===================================================================
# TestGoalAssessmentTool
# ===================================================================

class TestGoalAssessmentTool:
    def test_vague_when_no_retrieval_results(self):
        mgr = _mock_search_rag_manager([])
        tool = create_goal_assessment_tool(mgr)
        result = tool.invoke({"learning_goal": "learn stuff"})
        assert result["is_vague"] is True

    def test_not_vague_when_results_exist(self):
        mgr = _mock_search_rag_manager([_make_doc("Python basics")])
        tool = create_goal_assessment_tool(mgr)
        result = tool.invoke({"learning_goal": "learn Python"})
        assert result["is_vague"] is False

    def test_all_mastered_when_no_gaps(self):
        mgr = _mock_search_rag_manager([_make_doc("content")])
        tool = create_goal_assessment_tool(mgr)
        skill_gaps = [
            {"name": "Python", "is_gap": False},
            {"name": "SQL", "is_gap": False},
        ]
        result = tool.invoke({"learning_goal": "learn Python", "skill_gaps": skill_gaps})
        assert result["all_mastered"] is True

    def test_not_all_mastered_when_gaps_exist(self):
        mgr = _mock_search_rag_manager([_make_doc("content")])
        tool = create_goal_assessment_tool(mgr)
        skill_gaps = [
            {"name": "Python", "is_gap": True},
            {"name": "SQL", "is_gap": False},
        ]
        result = tool.invoke({"learning_goal": "learn Python", "skill_gaps": skill_gaps})
        assert result["all_mastered"] is False

    def test_suggestion_for_vague_goal(self):
        mgr = _mock_search_rag_manager([])
        tool = create_goal_assessment_tool(mgr)
        result = tool.invoke({"learning_goal": "learn stuff"})
        assert "vague" in result["suggestion"].lower() or "specific" in result["suggestion"].lower()

    def test_suggestion_for_all_mastered(self):
        mgr = _mock_search_rag_manager([_make_doc("content")])
        tool = create_goal_assessment_tool(mgr)
        skill_gaps = [{"name": "Python", "is_gap": False}]
        result = tool.invoke({"learning_goal": "learn Python", "skill_gaps": skill_gaps})
        assert "master" in result["suggestion"].lower() or "advanced" in result["suggestion"].lower()

    def test_works_with_no_skill_gaps(self):
        mgr = _mock_search_rag_manager([_make_doc("content")])
        tool = create_goal_assessment_tool(mgr)
        result = tool.invoke({"learning_goal": "learn Python"})
        assert result["all_mastered"] is False


# ===================================================================
# TestGoalRefinementTool
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
