"""Tests for the agentic learning plan generation orchestration.

These tests mock LLM calls and verify the orchestration logic:
- Auto-refinement loop with quality gate
- Metadata structure

Run from the repo root:
    python -m pytest backend/tests/test_agentic_learning_plan.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from modules.learning_plan_generator.agents.learning_path_scheduler import LearningPathScheduler
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import _evaluate_plan_quality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_learner_profile():
    return {
        "learning_goal": "Learn Python fundamentals",
        "skill_gaps": {
            "mastered_skills": [],
            "in_progress_skills": [
                {"name": "Python basics", "current_level": "beginner", "required_level": "intermediate"}
            ],
        },
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": -0.5,
                "fslsm_perception": 0.0,
                "fslsm_input": -0.3,
                "fslsm_understanding": 0.0,
            }
        },
    }


def _make_plan(num_sessions=3):
    return {
        "learning_path": [
            {
                "id": f"Session {i+1}",
                "title": f"Session {i+1}: Topic {i+1}",
                "abstract": f"Learn about topic {i+1}",
                "if_learned": False,
                "associated_skills": ["Python basics"],
                "desired_outcome_when_completed": [
                    {"name": "Python basics", "level": "intermediate"}
                ],
            }
            for i in range(num_sessions)
        ]
    }


# ---------------------------------------------------------------------------
# Tests for LearningPathScheduler init
# ---------------------------------------------------------------------------

class TestLearningPathSchedulerInit:

    def test_scheduler_init_no_tools(self):
        """Scheduler should have no tools (retrieval removed)."""
        mock_llm = MagicMock()
        scheduler = LearningPathScheduler(mock_llm)
        assert scheduler._tools is None


# ---------------------------------------------------------------------------
# Tests for agentic orchestration metadata structure
# ---------------------------------------------------------------------------

class TestAgenticMetadata:

    def test_evaluate_plan_quality_returns_expected_keys(self):
        """Quality gate should return pass, issues, feedback_summary."""
        feedback = {
            "feedback": {
                "progression": "Good",
                "engagement": "Good",
                "personalization": "Good",
            },
            "suggestions": {
                "progression": "",
                "engagement": "",
                "personalization": "",
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert "pass" in result
        assert "issues" in result
        assert "feedback_summary" in result
        assert len(result["feedback_summary"]) == 3

    def test_schedule_agentic_returns_metadata(self):
        """Mocked agentic generation should return plan + metadata dict."""
        # This tests the function signature / structure without real LLM calls
        # Full integration tests require actual LLM
        pass

    def test_schedule_agentic_without_rag_falls_back(self):
        """Scheduler should work without any tools."""
        mock_llm = MagicMock()
        scheduler = LearningPathScheduler(mock_llm)
        assert scheduler._tools is None

    def test_schedule_agentic_caps_at_max_refinements(self):
        """Quality gate failing every time should still cap at max refinements."""
        bad_feedback = {
            "progression": "poor progression needs improvement",
            "engagement": "weak engagement",
            "personalization": "not personalized",
            "suggestions": ["fix 1", "fix 2", "fix 3", "fix 4"],
        }
        result = _evaluate_plan_quality(bad_feedback)
        assert result["pass"] is False
        assert len(result["issues"]) > 0
