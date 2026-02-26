"""Tests for deterministic SOLO guardrails in plan feedback simulation.

Run from repo root:
    python -m pytest backend/tests/test_plan_feedback_simulator.py -v
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learning_plan_generator.agents.plan_feedback_simulator import (
    LearningPlanFeedbackSimulator,
    build_deterministic_solo_audit,
)


def _base_feedback(
    *,
    is_acceptable=True,
    issues=None,
    directives="",
    progression_feedback="The learner would likely find the path well-paced.",
    progression_suggestion="",
):
    return {
        "feedback": {
            "progression": progression_feedback,
            "engagement": "The learner would likely stay engaged.",
            "personalization": "The path is generally aligned to learner needs.",
        },
        "suggestions": {
            "progression": progression_suggestion,
            "engagement": "",
            "personalization": "",
        },
        "is_acceptable": is_acceptable,
        "issues": issues or [],
        "improvement_directives": directives,
    }


def _valid_scaffold_path():
    return [
        {
            "id": "Session 3",
            "title": "Introduction to Functions",
            "desired_outcome_when_completed": [
                {"name": "Understanding and Using Functions", "level": "beginner"},
            ],
        },
        {
            "id": "Session 4",
            "title": "Basics of Code Decomposition",
            "desired_outcome_when_completed": [
                {"name": "Code Decomposition", "level": "beginner"},
            ],
        },
        {
            "id": "Session 5",
            "title": "Understanding Functions and Decomposition",
            "desired_outcome_when_completed": [
                {"name": "Understanding and Using Functions", "level": "intermediate"},
                {"name": "Code Decomposition", "level": "intermediate"},
            ],
        },
    ]


class TestDeterministicSOLOAudit:
    def test_valid_scaffold_has_no_violations(self):
        profile = {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}}
        audit = build_deterministic_solo_audit(profile, _valid_scaffold_path())

        assert audit["violation_count"] == 0
        assert audit["has_violations"] is False

    def test_unlearned_to_intermediate_is_violation(self):
        profile = {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}}
        path = [
            {
                "id": "Session 1",
                "title": "Jump Start",
                "desired_outcome_when_completed": [
                    {"name": "Functions", "level": "intermediate"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 1
        assert audit["violations"][0]["from_level"] == "unlearned"
        assert audit["violations"][0]["to_level"] == "intermediate"

    def test_beginner_to_advanced_is_violation(self):
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Abstraction in Programming",
                        "current_proficiency_level": "beginner",
                        "required_proficiency_level": "advanced",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Abstraction Sprint",
                "desired_outcome_when_completed": [
                    {"name": "Abstraction in Programming", "level": "advanced"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 1
        assert audit["violations"][0]["from_level"] == "beginner"
        assert audit["violations"][0]["to_level"] == "advanced"

    def test_skill_name_normalization_matches_equivalent_names(self):
        profile = {
            "cognitive_status": {
                "mastered_skills": [],
                "in_progress_skills": [
                    {
                        "name": "Understanding and Using Functions",
                        "current_proficiency_level": "beginner",
                        "required_proficiency_level": "intermediate",
                    }
                ],
            }
        }
        path = [
            {
                "id": "Session 1",
                "title": "Functions in Practice",
                "desired_outcome_when_completed": [
                    {"name": "understanding   using functions!!", "level": "intermediate"},
                ],
            }
        ]

        audit = build_deterministic_solo_audit(profile, path)
        assert audit["violation_count"] == 0


class TestFeedbackReconciliation:
    def test_feedback_path_corrects_contradictory_progression_when_no_violations(self, monkeypatch):
        captured = {}

        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            captured["input"] = input_dict
            return _base_feedback(
                is_acceptable=False,
                issues=[
                    "Pacing too fast for beginner level in later sessions",
                    "SOLO progression skipped for multiple skills",
                ],
                directives="Add 2 foundational sessions before advancing to intermediate content.",
                progression_feedback="The learner would likely struggle with abrupt SOLO jumps.",
                progression_suggestion="Add beginner sessions before moving ahead.",
            )

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path(
            {
                "learner_profile": {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}},
                "learning_path": _valid_scaffold_path(),
            }
        )

        assert "solo_audit" in captured["input"]
        assert captured["input"]["solo_audit"]["violation_count"] == 0
        assert output["is_acceptable"] is True
        assert output["issues"] == []
        assert output["improvement_directives"] == ""
        assert "no level-skipping transitions" in output["feedback"]["progression"]

    def test_feedback_path_forces_unacceptable_when_violations_are_missed(self, monkeypatch):
        def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
            return _base_feedback(
                is_acceptable=True,
                issues=[],
                directives="",
                progression_feedback="The learner would likely find the progression well-paced.",
                progression_suggestion="Keep current pacing.",
            )

        monkeypatch.setattr(LearningPlanFeedbackSimulator, "invoke", fake_invoke)

        simulator = LearningPlanFeedbackSimulator(MagicMock())
        output = simulator.feedback_path(
            {
                "learner_profile": {"cognitive_status": {"mastered_skills": [], "in_progress_skills": []}},
                "learning_path": [
                    {
                        "id": "Session 1",
                        "title": "Functions and Decomposition Deep Dive",
                        "desired_outcome_when_completed": [
                            {"name": "Understanding and Using Functions", "level": "advanced"},
                        ],
                    }
                ],
            }
        )

        assert output["is_acceptable"] is False
        assert any("SOLO progression skipped" in issue for issue in output["issues"])
        assert "at most one SOLO level" in output["improvement_directives"]
        assert "deterministic SOLO audit found" in output["feedback"]["progression"]
