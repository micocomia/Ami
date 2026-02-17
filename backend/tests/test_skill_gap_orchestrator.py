"""Tests for the skill gap orchestrator (auto-refinement loop).

Tests the identify_skill_gap_with_llm function with mocked agents and tools.

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


class TestAutoRefinementLoop:
    @patch("modules.skill_gap.agents.skill_gap_identifier.LearningGoalRefiner")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillGapIdentifier")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillRequirementMapper")
    @patch("modules.skill_gap.agents.skill_gap_identifier.create_goal_assessment_tool")
    def test_vague_goal_triggers_auto_refinement(
        self, mock_assess_tool_factory, mock_mapper_cls, mock_identifier_cls, mock_refiner_cls
    ):
        """When goal is assessed as vague, auto-refinement should trigger and retry."""
        from modules.skill_gap.agents.skill_gap_identifier import identify_skill_gap_with_llm

        # Mapper returns requirements
        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        # Identifier returns gaps without goal_assessment (so fallback runs)
        mock_identifier = mock_identifier_cls.return_value
        mock_identifier.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()

        # Assessment tool says vague on first call, not vague on second
        mock_assess_fn = MagicMock()
        mock_assess_fn.invoke.side_effect = [
            {"is_vague": True, "all_mastered": False, "suggestion": "Be more specific"},
            {"is_vague": False, "all_mastered": False, "suggestion": ""},
        ]
        mock_assess_tool_factory.return_value = mock_assess_fn

        # Refiner returns refined goal
        mock_refiner = mock_refiner_cls.return_value
        mock_refiner.refine_goal.return_value = {"refined_goal": "Learn Python for data science with Pandas"}

        mgr = MagicMock()
        llm = MagicMock()

        skill_gaps, reqs = identify_skill_gap_with_llm(
            llm, "learn stuff", "CS student", search_rag_manager=mgr
        )

        # Refiner should have been called
        mock_refiner.refine_goal.assert_called_once()
        # Mapper called twice (once per attempt)
        assert mock_mapper.map_goal_to_skill.call_count == 2
        # Goal assessment includes auto_refined info
        assert skill_gaps["goal_assessment"]["auto_refined"] is True
        assert skill_gaps["goal_assessment"]["original_goal"] == "learn stuff"

    @patch("modules.skill_gap.agents.skill_gap_identifier.LearningGoalRefiner")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillGapIdentifier")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillRequirementMapper")
    @patch("modules.skill_gap.agents.skill_gap_identifier.create_goal_assessment_tool")
    def test_non_vague_goal_no_refinement(
        self, mock_assess_tool_factory, mock_mapper_cls, mock_identifier_cls, mock_refiner_cls
    ):
        """A clear goal should not trigger refinement."""
        from modules.skill_gap.agents.skill_gap_identifier import identify_skill_gap_with_llm

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        mock_identifier = mock_identifier_cls.return_value
        mock_identifier.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()

        mock_assess_fn = MagicMock()
        mock_assess_fn.invoke.return_value = {"is_vague": False, "all_mastered": False, "suggestion": ""}
        mock_assess_tool_factory.return_value = mock_assess_fn

        mgr = MagicMock()
        llm = MagicMock()

        skill_gaps, reqs = identify_skill_gap_with_llm(
            llm, "Learn Python for data science", "CS student", search_rag_manager=mgr
        )

        mock_refiner_cls.assert_not_called()
        assert mock_mapper.map_goal_to_skill.call_count == 1

    @patch("modules.skill_gap.agents.skill_gap_identifier.LearningGoalRefiner")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillGapIdentifier")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillRequirementMapper")
    @patch("modules.skill_gap.agents.skill_gap_identifier.create_goal_assessment_tool")
    def test_all_mastered_goal_no_refinement(
        self, mock_assess_tool_factory, mock_mapper_cls, mock_identifier_cls, mock_refiner_cls
    ):
        """All-mastered goals should not trigger auto-refinement."""
        from modules.skill_gap.agents.skill_gap_identifier import identify_skill_gap_with_llm

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        mock_identifier = mock_identifier_cls.return_value
        mock_identifier.identify_skill_gap.return_value = MOCK_SKILL_GAPS_ALL_MASTERED.copy()

        mock_assess_fn = MagicMock()
        mock_assess_fn.invoke.return_value = {"is_vague": True, "all_mastered": True, "suggestion": "You've mastered it all"}
        mock_assess_tool_factory.return_value = mock_assess_fn

        mgr = MagicMock()
        llm = MagicMock()

        skill_gaps, reqs = identify_skill_gap_with_llm(
            llm, "learn stuff", "Expert programmer", search_rag_manager=mgr
        )

        mock_refiner_cls.assert_not_called()

    @patch("modules.skill_gap.agents.skill_gap_identifier.LearningGoalRefiner")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillGapIdentifier")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillRequirementMapper")
    @patch("modules.skill_gap.agents.skill_gap_identifier.create_goal_assessment_tool")
    def test_max_one_refinement(
        self, mock_assess_tool_factory, mock_mapper_cls, mock_identifier_cls, mock_refiner_cls
    ):
        """Even if still vague after refinement, should only refine once."""
        from modules.skill_gap.agents.skill_gap_identifier import identify_skill_gap_with_llm

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        mock_identifier = mock_identifier_cls.return_value
        mock_identifier.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()

        # Still vague after refinement
        mock_assess_fn = MagicMock()
        mock_assess_fn.invoke.return_value = {"is_vague": True, "all_mastered": False, "suggestion": "Still vague"}
        mock_assess_tool_factory.return_value = mock_assess_fn

        mock_refiner = mock_refiner_cls.return_value
        mock_refiner.refine_goal.return_value = {"refined_goal": "learn more stuff"}

        mgr = MagicMock()
        llm = MagicMock()

        skill_gaps, reqs = identify_skill_gap_with_llm(
            llm, "learn stuff", "student", search_rag_manager=mgr
        )

        # Refiner called exactly once
        mock_refiner.refine_goal.assert_called_once()
        # Mapper called twice (original + refined)
        assert mock_mapper.map_goal_to_skill.call_count == 2
        # Still returns is_vague since refinement didn't help
        assert skill_gaps["goal_assessment"].get("is_vague") is True

    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillGapIdentifier")
    @patch("modules.skill_gap.agents.skill_gap_identifier.SkillRequirementMapper")
    def test_auto_refinement_info_in_response(self, mock_mapper_cls, mock_identifier_cls):
        """Response should include goal_assessment even without search_rag_manager."""
        from modules.skill_gap.agents.skill_gap_identifier import identify_skill_gap_with_llm

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.map_goal_to_skill.return_value = MOCK_SKILL_REQUIREMENTS

        mock_identifier = mock_identifier_cls.return_value
        mock_identifier.identify_skill_gap.return_value = MOCK_SKILL_GAPS_WITH_GAPS.copy()

        llm = MagicMock()

        skill_gaps, reqs = identify_skill_gap_with_llm(
            llm, "Learn Python", "CS student", search_rag_manager=None
        )

        # goal_assessment should be present (even if empty dict when no mgr)
        assert "goal_assessment" in skill_gaps
