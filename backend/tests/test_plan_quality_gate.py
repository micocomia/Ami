"""Tests for the deterministic plan quality gate.

The simulation tool returns LearnerFeedback schema:
{
    "feedback": {"progression": "...", "engagement": "...", "personalization": "..."},
    "suggestions": {"progression": "...", "engagement": "...", "personalization": "..."},
    "simulation_metadata": {...}
}

Run from the repo root:
    python -m pytest backend/tests/test_plan_quality_gate.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import _evaluate_plan_quality


class TestPlanQualityGate:

    def test_quality_gate_passes_positive_feedback(self):
        """No negative signals should result in a pass."""
        feedback = {
            "feedback": {
                "progression": "Well-structured progression from basics to advanced topics.",
                "engagement": "High engagement with varied activities.",
                "personalization": "Tailored to the learner's visual preference.",
            },
            "suggestions": {
                "progression": "Minor: consider adding a recap session",
                "engagement": "",
                "personalization": "",
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert result["pass"] is True
        assert len(result["issues"]) == 0

    def test_quality_gate_fails_negative_feedback(self):
        """Negative keywords in feedback should trigger a fail."""
        feedback = {
            "feedback": {
                "progression": "The path has poor progression and needs improvement.",
                "engagement": "Content is monotonous and repetitive.",
                "personalization": "Not personalized to the learner.",
            },
            "suggestions": {
                "progression": "",
                "engagement": "",
                "personalization": "",
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert result["pass"] is False
        assert len(result["issues"]) > 0

    def test_quality_gate_extracts_issues(self):
        """Issues list should be populated from detected keywords."""
        feedback = {
            "feedback": {
                "progression": "The learning path is lacking structure.",
                "engagement": "Sessions are too easy for this learner.",
                "personalization": "Good personalization overall.",
            },
            "suggestions": {
                "progression": "",
                "engagement": "",
                "personalization": "",
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert result["pass"] is False
        assert "lacking" in result["issues"]
        assert "too easy" in result["issues"]

    def test_quality_gate_handles_non_dict(self):
        """Non-dict input should default to pass."""
        result = _evaluate_plan_quality("some string")
        assert result["pass"] is True

        result = _evaluate_plan_quality(None)
        assert result["pass"] is True

    def test_quality_gate_high_suggestion_count_list(self):
        """More than 3 suggestions as a list should flag an issue."""
        feedback = {
            "feedback": {
                "progression": "Good progression.",
                "engagement": "Good engagement.",
                "personalization": "Good personalization.",
            },
            "suggestions": [
                "Add recap", "Add quiz", "Add examples",
                "Add references", "Add summary",
            ],
        }
        result = _evaluate_plan_quality(feedback)
        assert result["pass"] is False
        assert any("high_suggestion_count" in issue for issue in result["issues"])

    def test_quality_gate_high_suggestion_count_dict(self):
        """More than 3 total suggestions in a dict should flag an issue."""
        feedback = {
            "feedback": {
                "progression": "Good.",
                "engagement": "Good.",
                "personalization": "Good.",
            },
            "suggestions": {
                "progression": ["fix A", "fix B"],
                "engagement": ["fix C", "fix D"],
                "personalization": [],
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert result["pass"] is False
        assert any("high_suggestion_count" in issue for issue in result["issues"])

    def test_quality_gate_extracts_feedback_summary(self):
        """Feedback summary should contain progression, engagement, personalization from nested feedback dict."""
        feedback = {
            "feedback": {
                "progression": "Strong progression.",
                "engagement": "High engagement.",
                "personalization": "Well personalized.",
            },
            "suggestions": {
                "progression": "",
                "engagement": "",
                "personalization": "",
            },
        }
        result = _evaluate_plan_quality(feedback)
        assert result["feedback_summary"]["progression"] == "Strong progression."
        assert result["feedback_summary"]["engagement"] == "High engagement."
        assert result["feedback_summary"]["personalization"] == "Well personalized."
