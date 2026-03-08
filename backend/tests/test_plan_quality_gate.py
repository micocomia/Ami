"""Tests for the LLM-based plan quality gate.

The simulation tool now returns LearnerPlanFeedback schema:
{
    "feedback": {"progression": "...", "engagement": "...", "personalization": "..."},
    "suggestions": {"progression": "...", "engagement": "...", "personalization": "..."},
    "is_acceptable": true,
    "issues": [],
    "improvement_directives": ""
}

The pipeline reads `is_acceptable`, `issues`, and `improvement_directives` directly
from the simulation feedback instead of running a deterministic keyword scan.

Run from the repo root:
    python -m pytest backend/tests/test_plan_quality_gate.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import (
    schedule_learning_path_agentic,
)


_DUMMY_PLAN = {
    "learning_path": [
        {
            "id": "Session 1",
            "title": "Introduction",
            "abstract": "Intro session",
            "if_learned": False,
            "associated_skills": ["Skill A"],
            "desired_outcome_when_completed": [{"name": "Skill A", "level": "beginner"}],
            "mastery_score": None,
            "is_mastered": False,
            "mastery_threshold": 60.0,
            "has_checkpoint_challenges": False,
            "thinking_time_buffer_minutes": 0,
            "session_sequence_hint": None,
            "navigation_mode": "linear",
        }
    ]
}

_LEARNER_PROFILE = {
    "learning_goal": "Learn Python",
    "cognitive_status": {"mastered_skills": [], "in_progress_skills": []},
    "learning_preferences": {"fslsm_dimensions": {"fslsm_processing": 0.0}},
    "behavioral_patterns": {},
}


def _make_mock_simulator(feedback_dict):
    """Return a mock simulator whose .feedback_path() returns feedback_dict."""
    mock_sim = MagicMock()
    mock_sim.feedback_path.return_value = feedback_dict
    return mock_sim


def _pipeline_patches(mock_simulator):
    """Return patches needed to run schedule_learning_path_agentic without real LLM calls."""
    return [
        patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ),
        patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ),
    ]


class TestPlanQualityGatePassthrough:
    """Tests that pipeline correctly reads quality from simulation feedback."""

    def test_is_acceptable_true_breaks_loop_after_first_attempt(self):
        """When is_acceptable=True, the pipeline should stop after 1 iteration."""
        acceptable_feedback = {
            "feedback": {
                "progression": "The learner would find the progression well-paced.",
                "engagement": "The learner would stay engaged throughout.",
                "personalization": "The path aligns with the learner's preferences.",
            },
            "suggestions": {
                "progression": "",
                "engagement": "",
                "personalization": "",
            },
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN
        mock_sim = _make_mock_simulator(acceptable_feedback)

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_sim,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        assert metadata["refinement_iterations"] == 1
        assert metadata["evaluation"]["pass"] is True
        mock_scheduler.schedule_session.assert_called_once()
        mock_scheduler.reflexion.assert_not_called()

    def test_is_acceptable_false_triggers_reflexion(self):
        """When is_acceptable=False, the pipeline should run reflexion on next attempt."""
        failing_feedback = {
            "feedback": {
                "progression": "The learner would struggle with the pacing.",
                "engagement": "The learner may disengage due to mismatched style.",
                "personalization": "The path does not account for the learner's FSLSM profile.",
            },
            "suggestions": {
                "progression": "Add foundational sessions.",
                "engagement": "Include checkpoint challenges.",
                "personalization": "Align navigation_mode with FSLSM values.",
            },
            "is_acceptable": False,
            "issues": ["Pacing too fast for beginner level", "Insufficient FSLSM alignment"],
            "improvement_directives": "Add 1-2 foundational sessions before Session 2.",
        }
        passing_feedback = {
            "feedback": {"progression": "Better now.", "engagement": "Good.", "personalization": "Good."},
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        mock_simulator = MagicMock()
        mock_simulator.feedback_path.side_effect = [failing_feedback, passing_feedback]

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN
        mock_scheduler.reflexion.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        assert metadata["refinement_iterations"] == 2
        mock_scheduler.reflexion.assert_called_once()

    def test_improvement_directives_passed_to_reflexion(self):
        """improvement_directives from simulation feedback must flow into reflexion call."""
        directives = "Add 1-2 foundational grammar sessions before Session 2."
        failing_feedback = {
            "feedback": {"progression": "Needs foundational support.", "engagement": "OK.", "personalization": "OK."},
            "suggestions": {"progression": "Add basics.", "engagement": "", "personalization": ""},
            "is_acceptable": False,
            "issues": ["Insufficient foundational support"],
            "improvement_directives": directives,
        }
        passing_feedback = {
            "feedback": {"progression": "Good.", "engagement": "Good.", "personalization": "Good."},
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        mock_simulator = MagicMock()
        mock_simulator.feedback_path.side_effect = [failing_feedback, passing_feedback]

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN
        mock_scheduler.reflexion.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        reflexion_call_kwargs = mock_scheduler.reflexion.call_args[0][0]
        assert reflexion_call_kwargs["evaluator_feedback"] == directives

    def test_non_dict_simulation_feedback_defaults_to_pass(self):
        """Non-dict simulation feedback should be treated as acceptable (pass=True)."""
        mock_simulator = MagicMock()
        mock_simulator.feedback_path.return_value = "unexpected string output"

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        assert metadata["evaluation"]["pass"] is True
        assert metadata["refinement_iterations"] == 1
        mock_scheduler.reflexion.assert_not_called()

    def test_issues_extracted_from_simulation_feedback(self):
        """quality['issues'] should be populated directly from simulation feedback."""
        issues_list = ["Pacing too fast for beginner level", "Insufficient FSLSM alignment"]
        failing_feedback = {
            "feedback": {"progression": "Poor fit.", "engagement": "Low.", "personalization": "Missing."},
            "suggestions": {"progression": "Slow down.", "engagement": "Add challenges.", "personalization": "Align."},
            "is_acceptable": False,
            "issues": issues_list,
            "improvement_directives": "Some directive.",
        }
        passing_feedback = {
            "feedback": {"progression": "Good.", "engagement": "Good.", "personalization": "Good."},
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        mock_simulator = MagicMock()
        mock_simulator.feedback_path.side_effect = [failing_feedback, passing_feedback]

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN
        mock_scheduler.reflexion.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        # After second iteration passes, final quality should reflect the passing feedback
        assert metadata["evaluation"]["pass"] is True
        assert metadata["evaluation"]["issues"] == []

    def test_feedback_summary_extracted_from_simulation_feedback(self):
        """quality['feedback_summary'] should come from the 'feedback' key in simulation output."""
        feedback_content = {
            "progression": "The learner would find the path well-paced.",
            "engagement": "High engagement expected.",
            "personalization": "Well tailored.",
        }
        feedback = {
            "feedback": feedback_content,
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        mock_simulator = MagicMock()
        mock_simulator.feedback_path.return_value = feedback

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            plan, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=2,
            )

        assert metadata["evaluation"]["feedback_summary"] == feedback_content

    def test_quality_gate_contract_unchanged_with_extra_simulator_fields(self):
        """Pipeline should ignore extra simulator fields and keep using gate contract keys."""
        feedback = {
            "feedback": {
                "progression": "Progression needs bridging.",
                "engagement": "Engagement is acceptable.",
                "personalization": "Personalization is acceptable.",
            },
            "suggestions": {"progression": "Add bridging.", "engagement": "", "personalization": ""},
            "is_acceptable": False,
            "issues": ["SOLO progression skipped for 1 skill transition(s)"],
            "improvement_directives": "Insert bridging sessions.",
            "solo_audit": {"violation_count": 1, "has_violations": True},
            "simulation_metadata": {"simulation_model": "gpt-4o-mini"},
        }

        mock_simulator = MagicMock()
        mock_simulator.feedback_path.return_value = feedback

        mock_scheduler = MagicMock()
        mock_scheduler.schedule_session.return_value = _DUMMY_PLAN

        with patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
            return_value=mock_scheduler,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
            return_value=mock_simulator,
        ), patch(
            "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
            return_value=MagicMock(),
        ):
            _, metadata = schedule_learning_path_agentic(
                llm=MagicMock(),
                learner_profile=_LEARNER_PROFILE,
                max_refinements=0,
            )

        assert metadata["evaluation"]["pass"] is False
        assert metadata["evaluation"]["issues"] == ["SOLO progression skipped for 1 skill transition(s)"]
