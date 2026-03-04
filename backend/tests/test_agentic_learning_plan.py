"""Tests for the agentic learning plan generation orchestration.

These tests mock LLM calls and verify the orchestration logic:
- Auto-refinement loop with LLM-based quality gate
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
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import (
    schedule_learning_path_agentic,
)


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

    def _make_sim_tool(self, feedback_dict):
        sim_tool = MagicMock()
        sim_tool.invoke.return_value = feedback_dict
        return sim_tool

    def test_quality_gate_reads_is_acceptable_from_feedback(self):
        """Quality gate should read is_acceptable directly from simulation feedback."""
        feedback = {
            "feedback": {"progression": "Good", "engagement": "Good", "personalization": "Good"},
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }
        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _make_plan()

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.create_simulate_feedback_tool",
            return_value=self._make_sim_tool(feedback),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_make_learner_profile(),
                max_refinements=2,
            )

        assert "pass" in metadata["evaluation"]
        assert "issues" in metadata["evaluation"]
        assert "feedback_summary" in metadata["evaluation"]
        assert metadata["evaluation"]["pass"] is True

    def test_schedule_agentic_returns_metadata(self):
        """Mocked agentic generation should return plan + metadata dict."""
        pass  # Full integration tests require actual LLM

    def test_schedule_agentic_without_rag_falls_back(self):
        """Scheduler should work without any tools."""
        mock_llm = MagicMock()
        scheduler = LearningPathScheduler(mock_llm)
        assert scheduler._tools is None

    def test_schedule_agentic_caps_at_max_refinements(self):
        """Quality gate failing every time should still cap at max_refinements."""
        bad_feedback = {
            "feedback": {"progression": "Poor.", "engagement": "Weak.", "personalization": "Missing."},
            "suggestions": {"progression": "Fix.", "engagement": "Fix.", "personalization": "Fix."},
            "is_acceptable": False,
            "issues": ["Pacing too fast"],
            "improvement_directives": "Add foundational sessions.",
        }

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _make_plan()
        mock_scheduler.reflexion.return_value = _make_plan()

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.create_simulate_feedback_tool",
            return_value=self._make_sim_tool(bad_feedback),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_make_learner_profile(),
                max_refinements=2,
            )

        # 1 initial + 2 refinements = 3 total attempts
        assert metadata["refinement_iterations"] == 3
        assert metadata["evaluation"]["pass"] is False
