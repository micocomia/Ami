"""Tests for the Chatbot Bias Auditor module."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from modules.ai_chatbot_tutor.schemas import (
    ChatbotBiasAuditResult,
    ChatbotBiasCategory,
    ChatbotBiasFlag,
    ChatbotBiasSeverity,
)
from modules.ai_chatbot_tutor.agents.chatbot_bias_auditor import (
    ChatbotBiasAuditor,
    audit_chatbot_bias_with_llm,
)


# ── Schema tests ────────────────────────────────────────────────────


class TestChatbotBiasAuditSchemas(unittest.TestCase):
    """Validate enum values and pydantic models."""

    def test_bias_categories(self):
        self.assertEqual(ChatbotBiasCategory.tone_bias.value, "tone_bias")
        self.assertEqual(ChatbotBiasCategory.language_bias.value, "language_bias")
        self.assertEqual(ChatbotBiasCategory.stereotype_bias.value, "stereotype_bias")
        self.assertEqual(ChatbotBiasCategory.cultural_assumption.value, "cultural_assumption")

    def test_severity_levels(self):
        self.assertEqual(ChatbotBiasSeverity.low.value, "low")
        self.assertEqual(ChatbotBiasSeverity.medium.value, "medium")
        self.assertEqual(ChatbotBiasSeverity.high.value, "high")

    def test_bias_flag_valid(self):
        flag = ChatbotBiasFlag(
            message_index=0,
            bias_category=ChatbotBiasCategory.tone_bias,
            severity=ChatbotBiasSeverity.medium,
            explanation="The response is patronizing.",
            suggestion="Use a more respectful tone.",
        )
        self.assertEqual(flag.message_index, 0)
        self.assertEqual(flag.bias_category, ChatbotBiasCategory.tone_bias)

    def test_bias_flag_explanation_word_limit(self):
        with self.assertRaises(Exception):
            ChatbotBiasFlag(
                message_index=0,
                bias_category=ChatbotBiasCategory.tone_bias,
                severity=ChatbotBiasSeverity.low,
                explanation=" ".join(["word"] * 41),
                suggestion="Fix it.",
            )

    def test_bias_flag_suggestion_word_limit(self):
        with self.assertRaises(Exception):
            ChatbotBiasFlag(
                message_index=0,
                bias_category=ChatbotBiasCategory.tone_bias,
                severity=ChatbotBiasSeverity.low,
                explanation="Short explanation.",
                suggestion=" ".join(["word"] * 31),
            )

    def test_audit_result_defaults(self):
        result = ChatbotBiasAuditResult()
        self.assertEqual(result.bias_flags, [])
        self.assertEqual(result.deterministic_flags, [])
        self.assertEqual(result.overall_bias_risk, ChatbotBiasSeverity.low)
        self.assertEqual(result.audited_message_count, 0)
        self.assertEqual(result.flagged_message_count, 0)
        self.assertIn("AI system", result.ethical_disclaimer)


# ── Deterministic biased language check tests ───────────────────────


class TestBiasedLanguageCheck(unittest.TestCase):
    """Test the deterministic biased-phrase scanner."""

    def test_detects_mankind(self):
        flags = ChatbotBiasAuditor._check_biased_language("This benefits all mankind.")
        phrases = [f.explanation for f in flags]
        self.assertTrue(any("mankind" in p for p in phrases))

    def test_detects_chairman(self):
        flags = ChatbotBiasAuditor._check_biased_language("The chairman decided.")
        self.assertTrue(len(flags) >= 1)

    def test_detects_suffers_from(self):
        flags = ChatbotBiasAuditor._check_biased_language("She suffers from a condition.")
        self.assertTrue(any("suffers from" in f.explanation for f in flags))

    def test_no_false_positive_clean_text(self):
        flags = ChatbotBiasAuditor._check_biased_language(
            "Let me explain this concept step by step."
        )
        self.assertEqual(len(flags), 0)

    def test_case_insensitive(self):
        flags = ChatbotBiasAuditor._check_biased_language("MANKIND is great.")
        self.assertTrue(len(flags) >= 1)

    def test_all_flags_are_language_bias(self):
        flags = ChatbotBiasAuditor._check_biased_language("The fireman and the policeman.")
        for flag in flags:
            self.assertEqual(flag.bias_category, ChatbotBiasCategory.language_bias)
            self.assertEqual(flag.severity, ChatbotBiasSeverity.low)


# ── Deterministic patronizing language check tests ──────────────────


class TestPatronizingPhraseCheck(unittest.TestCase):
    """Test the deterministic patronizing-phrase scanner."""

    def test_detects_obviously(self):
        flags = ChatbotBiasAuditor._check_patronizing_language(
            "Obviously, this is how it works."
        )
        self.assertTrue(len(flags) >= 1)
        self.assertEqual(flags[0].bias_category, ChatbotBiasCategory.tone_bias)

    def test_detects_this_is_easy(self):
        flags = ChatbotBiasAuditor._check_patronizing_language(
            "This is easy, just follow along."
        )
        self.assertTrue(len(flags) >= 1)

    def test_detects_surely_you_know(self):
        flags = ChatbotBiasAuditor._check_patronizing_language(
            "Surely you know this already."
        )
        self.assertTrue(len(flags) >= 1)

    def test_no_false_positive_clean_text(self):
        flags = ChatbotBiasAuditor._check_patronizing_language(
            "Great question! Let me walk you through this concept."
        )
        self.assertEqual(len(flags), 0)

    def test_patronizing_flags_are_medium_severity(self):
        flags = ChatbotBiasAuditor._check_patronizing_language(
            "This is really simple to understand."
        )
        for flag in flags:
            self.assertEqual(flag.severity, ChatbotBiasSeverity.medium)


# ── Message counting tests ──────────────────────────────────────────


class TestMessageCounting(unittest.TestCase):
    """Test the tutor message counting logic."""

    def test_count_with_markers(self):
        text = "assistant: Hello\nassistant: How can I help?"
        count = ChatbotBiasAuditor._count_tutor_messages(text)
        self.assertEqual(count, 2)

    def test_count_single_response(self):
        text = "Let me explain this concept to you."
        count = ChatbotBiasAuditor._count_tutor_messages(text)
        self.assertGreaterEqual(count, 1)

    def test_count_with_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        count = ChatbotBiasAuditor._count_tutor_messages(text)
        self.assertEqual(count, 3)


# ── Agent tests with mocked LLM ────────────────────────────────────


class TestChatbotBiasAuditorAgent(unittest.TestCase):
    """Test the ChatbotBiasAuditor agent with a mocked LLM."""

    def _make_auditor(self, llm_response: dict) -> ChatbotBiasAuditor:
        mock_llm = MagicMock()
        auditor = ChatbotBiasAuditor(mock_llm)
        auditor.invoke = MagicMock(return_value=llm_response)
        return auditor

    def test_no_bias_detected(self):
        auditor = self._make_auditor({"bias_flags": [], "overall_bias_risk": "low"})
        result = auditor.audit_responses({
            "tutor_responses": "Great question! Let me help you understand recursion.",
            "learner_information": "Computer science student.",
        })
        self.assertEqual(result["overall_bias_risk"], "low")
        self.assertEqual(result["bias_flags"], [])
        self.assertEqual(result["deterministic_flags"], [])

    def test_llm_detects_bias(self):
        auditor = self._make_auditor({
            "bias_flags": [
                {
                    "message_index": 0,
                    "bias_category": "tone_bias",
                    "severity": "medium",
                    "explanation": "Response is condescending.",
                    "suggestion": "Use a more respectful tone.",
                }
            ],
            "overall_bias_risk": "medium",
        })
        result = auditor.audit_responses({
            "tutor_responses": "Some response text.",
            "learner_information": "A learner.",
        })
        self.assertEqual(result["overall_bias_risk"], "medium")
        self.assertEqual(len(result["bias_flags"]), 1)

    def test_deterministic_promotes_risk(self):
        auditor = self._make_auditor({"bias_flags": [], "overall_bias_risk": "low"})
        result = auditor.audit_responses({
            "tutor_responses": "This benefits all mankind.",
            "learner_information": "A learner.",
        })
        # LLM said low, but deterministic found "mankind" -> promoted to medium
        self.assertEqual(result["overall_bias_risk"], "medium")
        self.assertTrue(len(result["deterministic_flags"]) >= 1)

    def test_patronizing_promotes_risk(self):
        auditor = self._make_auditor({"bias_flags": [], "overall_bias_risk": "low"})
        result = auditor.audit_responses({
            "tutor_responses": "Obviously, this is how it works.",
            "learner_information": "A learner.",
        })
        self.assertEqual(result["overall_bias_risk"], "medium")
        self.assertTrue(len(result["deterministic_flags"]) >= 1)

    def test_ethical_disclaimer_present(self):
        auditor = self._make_auditor({"bias_flags": [], "overall_bias_risk": "low"})
        result = auditor.audit_responses({
            "tutor_responses": "Let me explain.",
            "learner_information": "A learner.",
        })
        self.assertIn("AI system", result["ethical_disclaimer"])

    def test_combined_llm_and_deterministic_flags(self):
        auditor = self._make_auditor({
            "bias_flags": [
                {
                    "message_index": 0,
                    "bias_category": "stereotype_bias",
                    "severity": "medium",
                    "explanation": "Assumes skill level based on gender.",
                    "suggestion": "Base explanations on assessed proficiency.",
                }
            ],
            "overall_bias_risk": "medium",
        })
        result = auditor.audit_responses({
            "tutor_responses": "The fireman explained it simply.",
            "learner_information": "A learner.",
        })
        self.assertEqual(result["overall_bias_risk"], "medium")
        self.assertEqual(len(result["bias_flags"]), 1)
        self.assertTrue(len(result["deterministic_flags"]) >= 1)


# ── Convenience function test ───────────────────────────────────────


class TestAuditChatbotBiasWithLlm(unittest.TestCase):
    """Test the convenience function."""

    @patch("modules.ai_chatbot_tutor.agents.chatbot_bias_auditor.ChatbotBiasAuditor")
    def test_calls_audit_responses(self, MockAuditor):
        mock_instance = MagicMock()
        mock_instance.audit_responses.return_value = {"overall_bias_risk": "low"}
        MockAuditor.return_value = mock_instance

        result = audit_chatbot_bias_with_llm(
            MagicMock(), "Hello!", "A learner."
        )
        mock_instance.audit_responses.assert_called_once()
        self.assertEqual(result["overall_bias_risk"], "low")


if __name__ == "__main__":
    unittest.main()
