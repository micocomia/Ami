"""Tests for the Content Bias Auditor module.

Run from the repo root:
    python -m pytest backend/tests/test_content_bias_auditor.py -v
"""

import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.content_generator.schemas import (
    ContentBiasCategory,
    ContentBiasSeverity,
    ContentBiasFlag,
    ContentBiasAuditResult,
)
from modules.content_generator.agents.content_bias_auditor import (
    ContentBiasAuditor,
    audit_content_bias_with_llm,
)


# ── Fixtures ─────────────────────────────────────────────────────────

CLEAN_CONTENT = """
## Introduction to Python

Python is a versatile programming language used across many domains.

## Variables and Data Types

Variables store values. Python supports integers, floats, strings, and booleans.

## Control Flow

Use if/else statements and loops to control program execution.
"""

BIASED_CONTENT = """
## Introduction to Programming

Programming has traditionally been a field for mankind to solve complex problems.
A good chairman of any tech team needs to understand these fundamentals.

## Working with Data

People who suffer from learning difficulties may find this section challenging.
"""

LEARNER_INFO = "Alex Chen, BSc Computer Science, 2 years Python experience."


# ── Schema Tests ─────────────────────────────────────────────────────

class TestContentBiasAuditSchemas:

    def test_content_bias_category_values(self):
        expected = {
            "representation_bias", "language_bias",
            "difficulty_bias", "source_bias",
        }
        assert {c.value for c in ContentBiasCategory} == expected

    def test_content_bias_severity_values(self):
        assert {s.value for s in ContentBiasSeverity} == {"low", "medium", "high"}

    def test_content_bias_flag_valid(self):
        flag = ContentBiasFlag(
            section_title="Introduction",
            bias_category=ContentBiasCategory.language_bias,
            severity=ContentBiasSeverity.low,
            explanation="Uses gendered language.",
            suggestion="Use gender-neutral alternatives.",
        )
        assert flag.section_title == "Introduction"
        assert flag.bias_category == ContentBiasCategory.language_bias

    def test_content_bias_flag_explanation_too_long(self):
        with pytest.raises(ValueError, match="40 words"):
            ContentBiasFlag(
                section_title="Intro",
                bias_category=ContentBiasCategory.language_bias,
                severity=ContentBiasSeverity.medium,
                explanation=" ".join(["word"] * 41),
                suggestion="Fix it.",
            )

    def test_content_bias_flag_suggestion_too_long(self):
        with pytest.raises(ValueError, match="30 words"):
            ContentBiasFlag(
                section_title="Intro",
                bias_category=ContentBiasCategory.language_bias,
                severity=ContentBiasSeverity.medium,
                explanation="Valid explanation.",
                suggestion=" ".join(["word"] * 31),
            )

    def test_content_bias_audit_result_defaults(self):
        result = ContentBiasAuditResult()
        assert result.bias_flags == []
        assert result.deterministic_flags == []
        assert result.overall_bias_risk == ContentBiasSeverity.low
        assert result.audited_section_count == 0
        assert result.flagged_section_count == 0
        assert "AI system" in result.ethical_disclaimer


# ── Biased Language Check Tests ──────────────────────────────────────

class TestBiasedLanguageCheck:

    def test_detects_mankind(self):
        flags = ContentBiasAuditor._check_biased_language("This is a great achievement for mankind.")
        phrases = [f.explanation for f in flags]
        assert any("mankind" in p for p in phrases)

    def test_detects_chairman(self):
        flags = ContentBiasAuditor._check_biased_language("The chairman will decide.")
        phrases = [f.explanation for f in flags]
        assert any("chairman" in p for p in phrases)

    def test_detects_suffers_from(self):
        flags = ContentBiasAuditor._check_biased_language("She suffers from a disability.")
        phrases = [f.explanation for f in flags]
        assert any("suffers from" in p for p in phrases)

    def test_detects_confined_to_wheelchair(self):
        flags = ContentBiasAuditor._check_biased_language("He is confined to a wheelchair.")
        phrases = [f.explanation for f in flags]
        assert any("confined to a wheelchair" in p for p in phrases)

    def test_clean_content_no_flags(self):
        flags = ContentBiasAuditor._check_biased_language(CLEAN_CONTENT)
        assert len(flags) == 0

    def test_empty_input(self):
        flags = ContentBiasAuditor._check_biased_language("")
        assert flags == []

    def test_multiple_biased_terms(self):
        text = "Mankind has always had a chairman to lead. The fireman was brave."
        flags = ContentBiasAuditor._check_biased_language(text)
        assert len(flags) == 3

    def test_flags_have_correct_category(self):
        flags = ContentBiasAuditor._check_biased_language("The policeman arrived.")
        assert len(flags) == 1
        assert flags[0].bias_category == ContentBiasCategory.language_bias

    def test_flags_suggest_alternatives(self):
        flags = ContentBiasAuditor._check_biased_language("The fireman responded quickly.")
        assert len(flags) == 1
        assert "firefighter" in flags[0].suggestion


# ── Section Count Tests ──────────────────────────────────────────────

class TestSectionCount:

    def test_counts_markdown_headers(self):
        count = ContentBiasAuditor._count_sections(CLEAN_CONTENT)
        assert count == 3

    def test_no_headers_returns_one(self):
        count = ContentBiasAuditor._count_sections("Just plain text with no headers.")
        assert count == 1

    def test_empty_content_returns_one(self):
        count = ContentBiasAuditor._count_sections("")
        assert count == 1


# ── Agent Tests (mocked LLM) ────────────────────────────────────────

class TestContentBiasAuditorAgent:

    def _make_auditor(self, llm_return_value):
        """Create a ContentBiasAuditor with a mocked invoke method."""
        mock_llm = MagicMock()
        with patch.object(ContentBiasAuditor, "__init__", lambda self, model: None):
            auditor = ContentBiasAuditor.__new__(ContentBiasAuditor)
            auditor._model = mock_llm
            auditor.invoke = MagicMock(return_value=llm_return_value)
        return auditor

    def test_clean_content_no_flags(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_content({
            "generated_content": CLEAN_CONTENT,
            "learner_information": LEARNER_INFO,
        })
        assert result["bias_flags"] == []
        assert result["deterministic_flags"] == []
        assert result["overall_bias_risk"] == "low"
        assert result["audited_section_count"] == 3
        assert result["flagged_section_count"] == 0
        assert "AI system" in result["ethical_disclaimer"]

    def test_llm_bias_flags_detected(self):
        auditor = self._make_auditor({
            "bias_flags": [
                {
                    "section_title": "Introduction",
                    "bias_category": "representation_bias",
                    "severity": "medium",
                    "explanation": "Examples are culturally narrow.",
                    "suggestion": "Include diverse cultural examples.",
                }
            ],
            "overall_bias_risk": "medium",
        })
        result = auditor.audit_content({
            "generated_content": CLEAN_CONTENT,
            "learner_information": LEARNER_INFO,
        })
        assert len(result["bias_flags"]) == 1
        assert result["bias_flags"][0]["bias_category"] == "representation_bias"
        assert result["overall_bias_risk"] == "medium"
        assert result["flagged_section_count"] == 1

    def test_deterministic_flags_merged(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_content({
            "generated_content": BIASED_CONTENT,
            "learner_information": LEARNER_INFO,
        })
        assert len(result["deterministic_flags"]) >= 2  # mankind, chairman, suffers from

    def test_risk_promoted_when_deterministic_flags_exist(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_content({
            "generated_content": BIASED_CONTENT,
            "learner_information": LEARNER_INFO,
        })
        # LLM said "low" but deterministic flags should promote to "medium"
        assert result["overall_bias_risk"] == "medium"

    def test_ethical_disclaimer_present(self):
        auditor = self._make_auditor({
            "bias_flags": [],
            "overall_bias_risk": "low",
        })
        result = auditor.audit_content({
            "generated_content": CLEAN_CONTENT,
            "learner_information": LEARNER_INFO,
        })
        assert "AI system" in result["ethical_disclaimer"]
        assert len(result["ethical_disclaimer"]) > 20


# ── Convenience Function Tests ───────────────────────────────────────

class TestAuditContentBiasWithLlm:

    @patch.object(ContentBiasAuditor, "audit_content")
    @patch.object(ContentBiasAuditor, "__init__", return_value=None)
    def test_creates_auditor_and_returns_dict(self, mock_init, mock_audit):
        mock_audit.return_value = {
            "bias_flags": [],
            "deterministic_flags": [],
            "overall_bias_risk": "low",
            "audited_section_count": 3,
            "flagged_section_count": 0,
            "ethical_disclaimer": "Test disclaimer",
        }
        result = audit_content_bias_with_llm(
            MagicMock(), CLEAN_CONTENT, LEARNER_INFO
        )
        assert isinstance(result, dict)
        assert result["overall_bias_risk"] == "low"
        mock_init.assert_called_once()
        mock_audit.assert_called_once()
