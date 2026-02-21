"""Tests for skill gap schemas, including the new GoalAssessment model.

Run from the repo root:
    python -m pytest backend/tests/test_skill_gap_schemas.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError
from modules.skill_gap.schemas import GoalAssessment, SkillGaps, SkillGap


class TestGoalAssessmentSchema:
    def test_valid_goal_assessment_defaults(self):
        """GoalAssessment with all defaults should be valid."""
        ga = GoalAssessment()
        assert ga.is_vague is False
        assert ga.all_mastered is False
        assert ga.suggestion == ""
        assert ga.auto_refined is False
        assert ga.original_goal is None

    def test_valid_goal_assessment_all_fields(self):
        """GoalAssessment with explicit values should be valid."""
        ga = GoalAssessment(
            is_vague=True,
            all_mastered=False,
            suggestion="Make your goal more specific.",
            auto_refined=True,
            original_goal="learn stuff",
        )
        assert ga.is_vague is True
        assert ga.auto_refined is True
        assert ga.original_goal == "learn stuff"

    def test_skill_gaps_with_goal_assessment(self):
        """SkillGaps model should accept an optional goal_assessment."""
        data = {
            "skill_gaps": [
                {
                    "name": "Python",
                    "is_gap": True,
                    "required_level": "intermediate",
                    "current_level": "beginner",
                    "reason": "Limited experience",
                    "level_confidence": "medium",
                }
            ],
            "goal_assessment": {
                "is_vague": False,
                "all_mastered": False,
                "suggestion": "",
            },
        }
        sg = SkillGaps.model_validate(data)
        assert sg.goal_assessment is not None
        assert sg.goal_assessment.is_vague is False

    def test_skill_gaps_without_goal_assessment(self):
        """SkillGaps model should work without goal_assessment (backward compat)."""
        data = {
            "skill_gaps": [
                {
                    "name": "Python",
                    "is_gap": True,
                    "required_level": "intermediate",
                    "current_level": "beginner",
                    "reason": "Limited experience",
                    "level_confidence": "medium",
                }
            ],
        }
        sg = SkillGaps.model_validate(data)
        assert sg.goal_assessment is None
