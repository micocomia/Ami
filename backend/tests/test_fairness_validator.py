"""Tests for the Fairness Validator module.

Run from the repo root:
    python -m pytest backend/tests/test_fairness_validator.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.learner_profiler.schemas import (
    FairnessCategory,
    FairnessSeverity,
    FairnessFlag,
    FSLSMDeviationFlag,
    ProfileFairnessResult,
)
from modules.learner_profiler.agents.fairness_validator import (
    FairnessValidator,
    validate_profile_fairness_with_llm,
)


# ── Fixtures ─────────────────────────────────────────────────────────

CLEAN_PROFILE = {
    "learner_information": "Jane has 2 years of Python experience and completed data science coursework.",
    "learning_goal": "Learn machine learning",
    "cognitive_status": {
        "overall_progress": 30,
        "mastered_skills": [
            {"name": "Python Basics", "proficiency_level": "intermediate"},
        ],
        "in_progress_skills": [
            {
                "name": "Machine Learning",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "beginner",
            },
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": -0.7,
            "fslsm_perception": -0.5,
            "fslsm_input": -0.5,
            "fslsm_understanding": -0.5,
        },
        "additional_notes": "Prefers practical examples.",
    },
    "behavioral_patterns": {
        "system_usage_frequency": "3 times per week",
        "session_duration_engagement": "30 minutes average",
        "motivational_triggers": None,
        "additional_notes": None,
    },
}

DEVIATED_PROFILE = {
    "learner_information": "Bob is a software engineer with 5 years experience.",
    "learning_goal": "Learn data science",
    "cognitive_status": {
        "overall_progress": 20,
        "mastered_skills": [],
        "in_progress_skills": [
            {
                "name": "Statistics",
                "required_proficiency_level": "advanced",
                "current_proficiency_level": "beginner",
            },
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": 0.5,
            "fslsm_perception": 0.6,
            "fslsm_input": 0.3,
            "fslsm_understanding": 0.4,
        },
        "additional_notes": "As an engineer, prefers hands-on learning.",
    },
    "behavioral_patterns": {
        "system_usage_frequency": "Daily",
        "session_duration_engagement": "1 hour",
        "motivational_triggers": "Naturally inclined towards technical content.",
        "additional_notes": None,
    },
}

LEARNER_INFO = "Jane Doe, BSc Computer Science, 2 years Python experience."


# ── Schema Tests ─────────────────────────────────────────────────────

class TestFairnessSchemas:

    def test_fairness_category_values(self):
        expected = {
            "fslsm_unjustified_deviation", "solo_missing_justification",
            "confidence_without_evidence", "stereotypical_language",
        }
        assert {c.value for c in FairnessCategory} == expected

    def test_fairness_severity_values(self):
        assert {s.value for s in FairnessSeverity} == {"low", "medium", "high"}

    def test_fairness_flag_valid(self):
        flag = FairnessFlag(
            field_name="fslsm_processing",
            fairness_category=FairnessCategory.fslsm_unjustified_deviation,
            severity=FairnessSeverity.medium,
            explanation="Processing dimension shifted without evidence.",
            suggestion="Verify with learner background information.",
        )
        assert flag.field_name == "fslsm_processing"

    def test_fairness_flag_explanation_too_long(self):
        with pytest.raises(ValueError, match="40 words"):
            FairnessFlag(
                field_name="fslsm_processing",
                fairness_category=FairnessCategory.fslsm_unjustified_deviation,
                severity=FairnessSeverity.medium,
                explanation=" ".join(["word"] * 41),
                suggestion="Fix it.",
            )

    def test_fairness_flag_suggestion_too_long(self):
        with pytest.raises(ValueError, match="30 words"):
            FairnessFlag(
                field_name="fslsm_processing",
                fairness_category=FairnessCategory.fslsm_unjustified_deviation,
                severity=FairnessSeverity.medium,
                explanation="Valid explanation.",
                suggestion=" ".join(["word"] * 31),
            )

    def test_profile_fairness_result_defaults(self):
        result = ProfileFairnessResult()
        assert result.fairness_flags == []
        assert result.fslsm_deviation_flags == []
        assert result.overall_fairness_risk == FairnessSeverity.low
        assert result.checked_fields_count == 0
        assert result.flagged_fields_count == 0
        assert "AI" in result.ethical_disclaimer


# ── FSLSM Deviation Tests ──────────────────────────────────────────

class TestFSLSMDeviationCheck:

    def test_large_deviation_flagged(self):
        """Hands-on Explorer (processing=-0.7) vs profile (processing=0.5) -> deviation 1.2."""
        flags = FairnessValidator._check_fslsm_deviation(DEVIATED_PROFILE, "Hands-on Explorer")
        processing_flags = [f for f in flags if f.dimension == "fslsm_processing"]
        assert len(processing_flags) == 1
        assert processing_flags[0].deviation == 1.2

    def test_all_dimensions_checked(self):
        """All 4 dimensions deviate significantly from Hands-on Explorer."""
        flags = FairnessValidator._check_fslsm_deviation(DEVIATED_PROFILE, "Hands-on Explorer")
        flagged_dims = {f.dimension for f in flags}
        assert "fslsm_processing" in flagged_dims
        assert "fslsm_perception" in flagged_dims

    def test_matching_persona_not_flagged(self):
        """Profile matches Hands-on Explorer baseline -> no flags."""
        flags = FairnessValidator._check_fslsm_deviation(CLEAN_PROFILE, "Hands-on Explorer")
        assert len(flags) == 0

    def test_small_deviation_not_flagged(self):
        """Deviation of 0.3 (below threshold of 0.4) -> not flagged."""
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": -0.4,
                    "fslsm_perception": -0.5,
                    "fslsm_input": -0.5,
                    "fslsm_understanding": -0.5,
                },
            },
        }
        flags = FairnessValidator._check_fslsm_deviation(profile, "Hands-on Explorer")
        assert len(flags) == 0

    def test_no_persona_skips_check(self):
        flags = FairnessValidator._check_fslsm_deviation(DEVIATED_PROFILE, "")
        assert flags == []

    def test_unknown_persona_skips_check(self):
        flags = FairnessValidator._check_fslsm_deviation(DEVIATED_PROFILE, "Unknown Persona")
        assert flags == []

    def test_balanced_learner_no_deviation(self):
        """Balanced Learner (all 0.0) vs profile (all 0.0) -> no flags."""
        profile = {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": 0.0,
                    "fslsm_perception": 0.0,
                    "fslsm_input": 0.0,
                    "fslsm_understanding": 0.0,
                },
            },
        }
        flags = FairnessValidator._check_fslsm_deviation(profile, "Balanced Learner")
        assert len(flags) == 0


# ── Stereotype Keyword Tests ───────────────────────────────────────

class TestStereotypeKeywordCheck:

    def test_stereotype_in_additional_notes(self):
        flags = FairnessValidator._check_stereotype_keywords(DEVIATED_PROFILE)
        field_names = [f["field_name"] for f in flags]
        assert "learning_preferences.additional_notes" in field_names

    def test_stereotype_in_motivational_triggers(self):
        flags = FairnessValidator._check_stereotype_keywords(DEVIATED_PROFILE)
        field_names = [f["field_name"] for f in flags]
        assert "behavioral_patterns.motivational_triggers" in field_names

    def test_clean_profile_no_flags(self):
        flags = FairnessValidator._check_stereotype_keywords(CLEAN_PROFILE)
        assert len(flags) == 0

    def test_empty_fields_no_flags(self):
        profile = {
            "learner_information": "",
            "learning_preferences": {"additional_notes": None},
            "behavioral_patterns": {"additional_notes": None, "motivational_triggers": None},
        }
        flags = FairnessValidator._check_stereotype_keywords(profile)
        assert flags == []

    def test_multiple_phrases_multiple_flags(self):
        profile = {
            "learner_information": "As an engineer, naturally inclined towards technical work.",
            "learning_preferences": {"additional_notes": None},
            "behavioral_patterns": {"additional_notes": None, "motivational_triggers": None},
        }
        flags = FairnessValidator._check_stereotype_keywords(profile)
        assert len(flags) == 2


# ── Agent Tests (mocked LLM) ───────────────────────────────────────

class TestFairnessValidatorAgent:

    def _make_validator(self, llm_return_value):
        """Create a FairnessValidator with a mocked invoke method."""
        mock_llm = MagicMock()
        with patch.object(FairnessValidator, "__init__", lambda self, model: None):
            validator = FairnessValidator.__new__(FairnessValidator)
            validator._model = mock_llm
            validator.invoke = MagicMock(return_value=llm_return_value)
        return validator

    def test_clean_profile_no_flags(self):
        validator = self._make_validator({
            "fairness_flags": [],
            "overall_fairness_risk": "low",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": CLEAN_PROFILE,
            "persona_name": "Hands-on Explorer",
        })
        assert result["fairness_flags"] == []
        assert result["overall_fairness_risk"] == "low"
        assert result["flagged_fields_count"] == 0
        assert "AI" in result["ethical_disclaimer"]

    def test_fairness_flags_detected(self):
        validator = self._make_validator({
            "fairness_flags": [
                {
                    "field_name": "fslsm_processing",
                    "fairness_category": "fslsm_unjustified_deviation",
                    "severity": "medium",
                    "explanation": "Processing set to reflective without evidence.",
                    "suggestion": "Use persona baseline unless evidence supports change.",
                }
            ],
            "overall_fairness_risk": "medium",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": CLEAN_PROFILE,
            "persona_name": "Hands-on Explorer",
        })
        assert len(result["fairness_flags"]) == 1
        assert result["overall_fairness_risk"] == "medium"
        assert result["flagged_fields_count"] == 1

    def test_fslsm_deviation_flags_merged(self):
        validator = self._make_validator({
            "fairness_flags": [],
            "overall_fairness_risk": "low",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": DEVIATED_PROFILE,
            "persona_name": "Hands-on Explorer",
        })
        assert len(result["fslsm_deviation_flags"]) > 0
        # Deviation flags should also appear in fairness_flags
        assert len(result["fairness_flags"]) > 0

    def test_stereotype_flags_merged(self):
        validator = self._make_validator({
            "fairness_flags": [],
            "overall_fairness_risk": "low",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": DEVIATED_PROFILE,
            "persona_name": "",
        })
        stereotype_flags = [
            f for f in result["fairness_flags"]
            if f.get("fairness_category") == "stereotypical_language"
        ]
        assert len(stereotype_flags) >= 2

    def test_risk_promoted_when_deterministic_flags_exist(self):
        validator = self._make_validator({
            "fairness_flags": [],
            "overall_fairness_risk": "low",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": DEVIATED_PROFILE,
            "persona_name": "Hands-on Explorer",
        })
        # LLM said "low" but deterministic flags should promote to "medium"
        assert result["overall_fairness_risk"] == "medium"

    def test_ethical_disclaimer_present(self):
        validator = self._make_validator({
            "fairness_flags": [],
            "overall_fairness_risk": "low",
        })
        result = validator.validate_profile({
            "learner_information": LEARNER_INFO,
            "learner_profile": CLEAN_PROFILE,
            "persona_name": "",
        })
        assert "AI" in result["ethical_disclaimer"]
        assert len(result["ethical_disclaimer"]) > 20


# ── Convenience Function Tests ──────────────────────────────────────

class TestValidateProfileFairnessWithLlm:

    @patch.object(FairnessValidator, "validate_profile")
    @patch.object(FairnessValidator, "__init__", return_value=None)
    def test_creates_validator_and_returns_dict(self, mock_init, mock_validate):
        mock_validate.return_value = {
            "fairness_flags": [],
            "fslsm_deviation_flags": [],
            "overall_fairness_risk": "low",
            "checked_fields_count": 10,
            "flagged_fields_count": 0,
            "ethical_disclaimer": "Test disclaimer",
        }
        result = validate_profile_fairness_with_llm(
            MagicMock(), LEARNER_INFO, CLEAN_PROFILE, "Hands-on Explorer"
        )
        assert isinstance(result, dict)
        assert result["overall_fairness_risk"] == "low"
        mock_init.assert_called_once()
        mock_validate.assert_called_once()
