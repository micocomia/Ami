"""Tests for scoped profile update functions (cognitive-only and preferences-only).

Run from the repo root:
    python -m pytest backend/tests/test_scoped_profile_updates.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import copy
import pytest
from unittest.mock import MagicMock, patch

from modules.learner_profiler.agents.adaptive_learning_profiler import (
    AdaptiveLearnerProfiler,
    CognitiveUpdatePayload,
    PreferencesUpdatePayload,
    update_cognitive_status_with_llm,
    update_learner_information_with_llm,
    update_learning_preferences_with_llm,
)

SAMPLE_PROFILE = {
    "learner_information": "CS student with Python background",
    "learning_goal": "Learn Data Science",
    "goal_display_name": "Data Science",
    "cognitive_status": {
        "overall_progress": 30,
        "mastered_skills": [
            {"name": "Python Basics", "proficiency_level": "advanced"}
        ],
        "in_progress_skills": [
            {
                "name": "Data Analysis",
                "required_proficiency_level": "intermediate",
                "current_proficiency_level": "beginner",
            },
            {
                "name": "Machine Learning",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            },
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": 0.0,
            "fslsm_perception": 0.0,
            "fslsm_input": 0.0,
            "fslsm_understanding": 0.0,
        },
        "additional_notes": "No strong preference yet",
    },
    "behavioral_patterns": {
        "system_usage_frequency": "3 logins/week",
        "session_duration_engagement": "25 min avg",
        "motivational_triggers": "None",
        "additional_notes": "",
    },
}


def _make_mock_llm(return_profile):
    """Create a mock LLM that makes AdaptiveLearnerProfiler.invoke return the given profile."""
    mock_llm = MagicMock()
    return mock_llm, return_profile


class TestCognitiveUpdatePreservesPreferences:
    def test_cognitive_update_preserves_preferences(self):
        """Calling update_cognitive_status should not change learning_preferences."""
        # Simulate LLM returning a profile with updated cognitive status
        updated = copy.deepcopy(SAMPLE_PROFILE)
        updated["cognitive_status"]["overall_progress"] = 50
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Data Analysis", "proficiency_level": "intermediate"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            {
                "name": "Machine Learning",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                {"id": "Session 2", "if_learned": True, "desired_outcome_when_completed": [{"name": "Data Analysis", "level": "intermediate"}]},
            )

        # Preferences should be identical to original
        assert result["learning_preferences"]["fslsm_dimensions"] == SAMPLE_PROFILE["learning_preferences"]["fslsm_dimensions"]
        # Cognitive status should have changed
        assert result["cognitive_status"]["overall_progress"] == 50
        assert len(result["cognitive_status"]["mastered_skills"]) == 2


class TestPreferencesUpdatePreservesCognitive:
    def test_preferences_update_preserves_cognitive(self):
        """Calling update_learning_preferences should not change cognitive_status."""
        updated = copy.deepcopy(SAMPLE_PROFILE)
        updated["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] = -0.7
        updated["learning_preferences"]["additional_notes"] = "Prefers visual content"

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_learning_preferences_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                {"feedback": "I am 100% a visual learner"},
                "",
            )

        # Cognitive status should be identical to original
        assert result["cognitive_status"] == SAMPLE_PROFILE["cognitive_status"]
        # Preferences should have changed
        assert result["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] == -0.7


class TestCognitiveUpdateMovesSkillToMastered:
    def test_cognitive_update_moves_skill_to_mastered(self):
        """Session with if_learned=True and level >= required should move skill to mastered."""
        updated = copy.deepcopy(SAMPLE_PROFILE)
        # Move Data Analysis to mastered
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Data Analysis", "proficiency_level": "intermediate"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s for s in updated["cognitive_status"]["in_progress_skills"]
            if s["name"] != "Data Analysis"
        ]
        updated["cognitive_status"]["overall_progress"] = 50

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                {"id": "Session 2", "if_learned": True, "desired_outcome_when_completed": [{"name": "Data Analysis", "level": "intermediate"}]},
            )

        mastered_names = [s["name"] for s in result["cognitive_status"]["mastered_skills"]]
        in_progress_names = [s["name"] for s in result["cognitive_status"]["in_progress_skills"]]
        assert "Data Analysis" in mastered_names
        assert "Data Analysis" not in in_progress_names


class TestPreferencesUpdateAdjustsFSLSM:
    def test_preferences_update_adjusts_fslsm(self):
        """User feedback 'I am visual learner' should shift fslsm_input negative."""
        updated = copy.deepcopy(SAMPLE_PROFILE)
        updated["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] = -0.6

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_learning_preferences_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                {"feedback": "I am visual learner"},
                "",
            )

        assert result["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] < 0


class TestLearnerInformationUpdatePreservesEverythingElse:
    def test_info_update_preserves_non_info_fields(self):
        updated = copy.deepcopy(SAMPLE_PROFILE)
        updated["learner_information"] = "Updated learner information"
        # Simulate an LLM trying to modify protected sections.
        updated["cognitive_status"]["overall_progress"] = 99
        updated["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] = 0.9
        updated["behavioral_patterns"]["system_usage_frequency"] = "hourly"

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_learner_information_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                edited_learner_information="Updated learner information",
                resume_text="",
            )

        assert result["learner_information"] == "Updated learner information"
        assert result["cognitive_status"] == SAMPLE_PROFILE["cognitive_status"]
        assert result["learning_preferences"] == SAMPLE_PROFILE["learning_preferences"]
        assert result["behavioral_patterns"] == SAMPLE_PROFILE["behavioral_patterns"]

    def test_info_update_accepts_partial_llm_output_with_only_learner_information(self):
        partial = {"learner_information": "Updated from resume + manual edits"}

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=partial):
            result = update_learner_information_with_llm(
                mock_llm,
                SAMPLE_PROFILE,
                edited_learner_information="Updated from resume + manual edits",
                resume_text="",
            )

        assert result["learner_information"] == "Updated from resume + manual edits"
        assert result["learning_goal"] == SAMPLE_PROFILE["learning_goal"]
        assert result["cognitive_status"] == SAMPLE_PROFILE["cognitive_status"]
        assert result["learning_preferences"] == SAMPLE_PROFILE["learning_preferences"]
        assert result["behavioral_patterns"] == SAMPLE_PROFILE["behavioral_patterns"]


class TestCognitiveUpdateGuardrails:
    def test_premature_mastery_is_reverted(self):
        profile = copy.deepcopy(SAMPLE_PROFILE)
        profile["cognitive_status"]["in_progress_skills"].append(
            {
                "name": "Python",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
        )

        updated = copy.deepcopy(profile)
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Python", "proficiency_level": "beginner"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s for s in updated["cognitive_status"]["in_progress_skills"] if s["name"] != "Python"
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                profile,
                {
                    "id": "Session X",
                    "if_learned": True,
                    "desired_outcome_when_completed": [{"name": "Python", "level": "beginner"}],
                },
            )

        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        assert "Python" not in mastered_names

        in_progress = [
            s for s in result["cognitive_status"]["in_progress_skills"] if s["name"] == "Python"
        ]
        assert len(in_progress) == 1
        assert in_progress[0]["required_proficiency_level"] == "advanced"
        assert in_progress[0]["current_proficiency_level"] == "beginner"

    def test_legitimate_mastery_is_preserved(self):
        profile = copy.deepcopy(SAMPLE_PROFILE)

        updated = copy.deepcopy(profile)
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Data Analysis", "proficiency_level": "intermediate"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s for s in updated["cognitive_status"]["in_progress_skills"]
            if s["name"] != "Data Analysis"
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                profile,
                {
                    "id": "Session 2",
                    "if_learned": True,
                    "desired_outcome_when_completed": [{"name": "Data Analysis", "level": "intermediate"}],
                },
            )

        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        in_progress_names = {s["name"] for s in result["cognitive_status"]["in_progress_skills"]}
        assert "Data Analysis" in mastered_names
        assert "Data Analysis" not in in_progress_names

    def test_partial_completion_does_not_create_duplicate_in_progress(self):
        profile = copy.deepcopy(SAMPLE_PROFILE)
        profile["cognitive_status"]["in_progress_skills"].append(
            {
                "name": "Python",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
        )

        updated = copy.deepcopy(profile)
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Python", "proficiency_level": "beginner"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s if s["name"] != "Python" else {
                "name": "Python",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
            for s in updated["cognitive_status"]["in_progress_skills"]
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                profile,
                {
                    "id": "Session Y",
                    "if_learned": True,
                    "desired_outcome_when_completed": [{"name": "Python", "level": "beginner"}],
                },
            )

        in_progress = [
            s for s in result["cognitive_status"]["in_progress_skills"] if s["name"] == "Python"
        ]
        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        assert len(in_progress) == 1
        assert in_progress[0]["current_proficiency_level"] == "beginner"
        assert "Python" not in mastered_names

    def test_guardrail_uses_normalized_skill_name_matching(self):
        profile = copy.deepcopy(SAMPLE_PROFILE)
        profile["cognitive_status"]["in_progress_skills"].append(
            {
                "name": "Data Analysis",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
        )

        updated = copy.deepcopy(profile)
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "data-analysis!!", "proficiency_level": "beginner"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s for s in updated["cognitive_status"]["in_progress_skills"]
            if s["name"] != "Data Analysis"
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                profile,
                {
                    "id": "Session Z",
                    "if_learned": True,
                    "desired_outcome_when_completed": [{"name": "  Data   Analysis  ", "level": "beginner"}],
                },
            )

        in_progress = [
            s for s in result["cognitive_status"]["in_progress_skills"] if s["name"] == "Data Analysis"
        ]
        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        assert len(in_progress) == 1
        assert in_progress[0]["current_proficiency_level"] == "beginner"
        assert "data-analysis!!" not in mastered_names

    def test_guardrail_applies_only_when_if_learned_true(self):
        profile = copy.deepcopy(SAMPLE_PROFILE)
        profile["cognitive_status"]["in_progress_skills"].append(
            {
                "name": "Python",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "unlearned",
            }
        )

        updated = copy.deepcopy(profile)
        updated["cognitive_status"]["mastered_skills"].append(
            {"name": "Python", "proficiency_level": "beginner"}
        )
        updated["cognitive_status"]["in_progress_skills"] = [
            s for s in updated["cognitive_status"]["in_progress_skills"] if s["name"] != "Python"
        ]

        mock_llm = MagicMock()
        with patch.object(AdaptiveLearnerProfiler, "invoke", return_value=updated):
            result = update_cognitive_status_with_llm(
                mock_llm,
                profile,
                {
                    "id": "Session N",
                    "if_learned": False,
                    "desired_outcome_when_completed": [{"name": "Python", "level": "beginner"}],
                },
            )

        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        in_progress_names = {s["name"] for s in result["cognitive_status"]["in_progress_skills"]}
        assert "Python" in mastered_names
        assert "Python" not in in_progress_names


class TestPayloadValidation:
    def test_cognitive_payload_requires_fields(self):
        """CognitiveUpdatePayload should reject missing required fields."""
        with pytest.raises(Exception):
            CognitiveUpdatePayload()

        # Valid payload should pass
        payload = CognitiveUpdatePayload(
            learner_profile=SAMPLE_PROFILE,
            session_information={"id": "Session 1", "if_learned": True},
        )
        assert payload.learner_profile is not None

    def test_preferences_payload_requires_fields(self):
        """PreferencesUpdatePayload should reject missing required fields."""
        with pytest.raises(Exception):
            PreferencesUpdatePayload()

        # Valid payload should pass
        payload = PreferencesUpdatePayload(
            learner_profile=SAMPLE_PROFILE,
            learner_interactions={"feedback": "test"},
        )
        assert payload.learner_profile is not None
        # learner_information defaults to ""
        assert payload.learner_information == ""

    def test_cognitive_payload_rejects_invalid_profile(self):
        """CognitiveUpdatePayload should reject non-string/dict/mapping types for learner_profile."""
        with pytest.raises(Exception):
            CognitiveUpdatePayload(
                learner_profile=12345,
                session_information={"id": "Session 1"},
            )

    def test_preferences_payload_rejects_invalid_interactions(self):
        """PreferencesUpdatePayload should reject non-string/dict/mapping types for learner_interactions."""
        with pytest.raises(Exception):
            PreferencesUpdatePayload(
                learner_profile=SAMPLE_PROFILE,
                learner_interactions=12345,
            )
