"""Tests for the Bias Auditor module.

Run from the repo root:
    python -m pytest backend/tests/test_bias_auditor.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.skill_gap.schemas import (
    BiasCategory,
    BiasSeverity,
    BiasFlag,
    ConfidenceCalibrationFlag,
    BiasAuditResult,
)
from modules.skill_gap.agents.bias_auditor import (
    BiasAuditor,
    audit_skill_gap_bias_with_llm,
)


# ── Fixtures ─────────────────────────────────────────────────────────

CLEAN_SKILL_GAPS = {
    "skill_gaps": [
        {
            "name": "Python Basics",
            "is_gap": True,
            "required_level": "intermediate",
            "current_level": "beginner",
            "reason": "Limited project experience shown in resume.",
            "level_confidence": "medium",
        },
        {
            "name": "Data Structures",
            "is_gap": False,
            "required_level": "intermediate",
            "current_level": "intermediate",
            "reason": "Completed relevant coursework.",
            "level_confidence": "high",
        },
    ]
}

LOW_CONFIDENCE_EXTREME_SKILL_GAPS = {
    "skill_gaps": [
        {
            "name": "Machine Learning",
            "is_gap": True,
            "required_level": "advanced",
            "current_level": "unlearned",
            "reason": "No evidence of ML experience.",
            "level_confidence": "low",
        },
        {
            "name": "Statistics",
            "is_gap": False,
            "required_level": "advanced",
            "current_level": "expert",
            "reason": "Has a PhD in statistics.",
            "level_confidence": "low",
        },
    ]
}

LEARNER_INFO = "Jane Doe, BSc Computer Science from MIT, 2 years Python experience."


# ── Schema Tests ─────────────────────────────────────────────────────

class TestBiasAuditSchemas:

    def test_bias_category_values(self):
        expected = {
            "demographic_inference", "prestige_bias", "gender_assumption",
            "age_assumption", "nationality_assumption", "stereotype_based",
            "unsubstantiated_claim",
        }
        assert {c.value for c in BiasCategory} == expected

    def test_bias_severity_values(self):
        assert {s.value for s in BiasSeverity} == {"low", "medium", "high"}

    def test_bias_flag_valid(self):
        flag = BiasFlag(
            skill_name="Python",
            bias_category=BiasCategory.prestige_bias,
            severity=BiasSeverity.medium,
            explanation="Assessment influenced by prestigious university.",
            suggestion="Base assessment on demonstrated skills only.",
        )
        assert flag.skill_name == "Python"

    def test_bias_flag_explanation_too_long(self):
        with pytest.raises(ValueError, match="40 words"):
            BiasFlag(
                skill_name="Python",
                bias_category=BiasCategory.prestige_bias,
                severity=BiasSeverity.medium,
                explanation=" ".join(["word"] * 41),
                suggestion="Fix it.",
            )

    def test_bias_flag_suggestion_too_long(self):
        with pytest.raises(ValueError, match="30 words"):
            BiasFlag(
                skill_name="Python",
                bias_category=BiasCategory.prestige_bias,
                severity=BiasSeverity.medium,
                explanation="Valid explanation.",
                suggestion=" ".join(["word"] * 31),
            )

    def test_bias_audit_result_defaults(self):
        result = BiasAuditResult()
        assert result.bias_flags == []
        assert result.confidence_calibration_flags == []
        assert result.overall_bias_risk == BiasSeverity.low
        assert result.audited_skill_count == 0
        assert result.flagged_skill_count == 0
        assert "AI-generated" in result.ethical_disclaimer


# ── Confidence Calibration Tests ────────────────────────────────────

class TestConfidenceCalibration:

    def test_low_confidence_unlearned_flagged(self):
        gaps = [{"name": "ML", "current_level": "unlearned", "level_confidence": "low"}]
        flags = BiasAuditor._check_confidence_calibration(gaps)
        assert len(flags) == 1
        assert flags[0].skill_name == "ML"
        assert "extreme level" in flags[0].issue

    def test_low_confidence_expert_flagged(self):
        gaps = [{"name": "Stats", "current_level": "expert", "level_confidence": "low"}]
        flags = BiasAuditor._check_confidence_calibration(gaps)
        assert len(flags) == 1
        assert flags[0].skill_name == "Stats"

    def test_low_confidence_intermediate_not_flagged(self):
        gaps = [{"name": "Python", "current_level": "intermediate", "level_confidence": "low"}]
        flags = BiasAuditor._check_confidence_calibration(gaps)
        assert len(flags) == 0

    def test_medium_confidence_extreme_not_flagged(self):
        gaps = [{"name": "ML", "current_level": "unlearned", "level_confidence": "medium"}]
        flags = BiasAuditor._check_confidence_calibration(gaps)
        assert len(flags) == 0

    def test_high_confidence_extreme_not_flagged(self):
        gaps = [{"name": "ML", "current_level": "expert", "level_confidence": "high"}]
        flags = BiasAuditor._check_confidence_calibration(gaps)
        assert len(flags) == 0

    def test_empty_input(self):
        flags = BiasAuditor._check_confidence_calibration([])
        assert flags == []


# ── Agent Tests (mocked LLM) ───────────────────────────────────────

class TestBiasAuditorAgent:

    def _make_auditor(self, llm_return_value):
        """Create a BiasAuditor with a mocked invoke method."""
        mock_llm = MagicMock()
        with patch.object(BiasAuditor, "__init__", lambda self, model: None):
            auditor = BiasAuditor.__new__(BiasAuditor)
            auditor._model = mock_llm
            auditor.invoke = MagicMock(return_value=llm_return_value)
        return auditor

    def test_clean_assessment_no_flags(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_skill_gaps({
            "learner_information": LEARNER_INFO,
            "skill_gaps": CLEAN_SKILL_GAPS,
        })
        assert result["bias_flags"] == []
        assert result["overall_bias_risk"] == "low"
        assert result["audited_skill_count"] == 2
        assert result["flagged_skill_count"] == 0
        assert "AI-generated" in result["ethical_disclaimer"]

    def test_bias_flags_detected(self):
        auditor = self._make_auditor({
            "bias_flags": [
                {
                    "skill_name": "Python Basics",
                    "bias_category": "prestige_bias",
                    "severity": "medium",
                    "explanation": "Assessment boosted due to MIT attendance.",
                    "suggestion": "Evaluate based on demonstrated skills.",
                }
            ],
            "overall_bias_risk": "medium",
        })
        result = auditor.audit_skill_gaps({
            "learner_information": LEARNER_INFO,
            "skill_gaps": CLEAN_SKILL_GAPS,
        })
        assert len(result["bias_flags"]) == 1
        assert result["bias_flags"][0]["bias_category"] == "prestige_bias"
        assert result["overall_bias_risk"] == "medium"
        assert result["flagged_skill_count"] == 1

    def test_calibration_flags_merged(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_skill_gaps({
            "learner_information": LEARNER_INFO,
            "skill_gaps": LOW_CONFIDENCE_EXTREME_SKILL_GAPS,
        })
        assert len(result["confidence_calibration_flags"]) == 2
        assert result["audited_skill_count"] == 2

    def test_risk_promoted_when_calibration_flags_exist(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_skill_gaps({
            "learner_information": LEARNER_INFO,
            "skill_gaps": LOW_CONFIDENCE_EXTREME_SKILL_GAPS,
        })
        # LLM said "low" but calibration flags should promote to "medium"
        assert result["overall_bias_risk"] == "medium"

    def test_ethical_disclaimer_present(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_skill_gaps({
            "learner_information": LEARNER_INFO,
            "skill_gaps": CLEAN_SKILL_GAPS,
        })
        assert "AI-generated" in result["ethical_disclaimer"]
        assert len(result["ethical_disclaimer"]) > 20


# ── Convenience Function Tests ──────────────────────────────────────

class TestAuditSkillGapBiasWithLlm:

    @patch.object(BiasAuditor, "audit_skill_gaps")
    @patch.object(BiasAuditor, "__init__", return_value=None)
    def test_creates_auditor_and_returns_dict(self, mock_init, mock_audit):
        mock_audit.return_value = {
            "bias_flags": [],
            "confidence_calibration_flags": [],
            "overall_bias_risk": "low",
            "audited_skill_count": 2,
            "flagged_skill_count": 0,
            "ethical_disclaimer": "Test disclaimer",
        }
        result = audit_skill_gap_bias_with_llm(
            MagicMock(), LEARNER_INFO, CLEAN_SKILL_GAPS
        )
        assert isinstance(result, dict)
        assert result["overall_bias_risk"] == "low"
        mock_init.assert_called_once()
        mock_audit.assert_called_once()
