"""Tests for SOLO taxonomy evaluator.

Uses mocked LLM to avoid API key / network requirements.

Run from the repo root:
    python -m pytest backend/tests/test_solo_evaluator.py -v
"""

import sys
import os
import json
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils.solo_evaluator import (
    SOLOEvaluation,
    evaluate_free_text_response,
    evaluate_short_answer_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm(response_dict: dict) -> MagicMock:
    """Return a mock LLM that returns a JSON string for the given response dict."""
    mock = MagicMock()
    mock.invoke.return_value = json.dumps(response_dict)
    return mock


SAMPLE_QUESTION = "Explain how gradient descent relates to model training and predict what would happen if the learning rate were too high."
SAMPLE_RUBRIC = (
    "Prestructural: irrelevant answer. "
    "Unistructural: mentions gradient descent only. "
    "Multistructural: lists gradient descent and learning rate separately. "
    "Relational: explains how learning rate controls the update step size in gradient descent. "
    "Extended Abstract: predicts consequences (divergence) of too-high learning rate."
)
SAMPLE_EXAMPLE = (
    "Gradient descent iteratively adjusts model parameters to minimize loss. "
    "The learning rate controls the step size of each update. If too high, updates overshoot "
    "the minimum, causing the loss to diverge rather than converge."
)


# ---------------------------------------------------------------------------
# Tests for evaluate_free_text_response
# ---------------------------------------------------------------------------

class TestEvaluateFreeTextResponse:
    def test_prestructural_response(self):
        llm = _make_llm({"solo_level": "prestructural", "score": 0.0, "feedback": "Irrelevant."})
        result = evaluate_free_text_response(llm, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE, "I don't know.")
        assert isinstance(result, SOLOEvaluation)
        assert result.solo_level == "prestructural"
        assert result.score == 0.0
        assert "Irrelevant" in result.feedback

    def test_unistructural_response(self):
        llm = _make_llm({"solo_level": "unistructural", "score": 0.25, "feedback": "Mentions gradient descent only."})
        result = evaluate_free_text_response(llm, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE, "Gradient descent minimizes loss.")
        assert result.solo_level == "unistructural"
        assert result.score == pytest.approx(0.25)

    def test_multistructural_response(self):
        llm = _make_llm({"solo_level": "multistructural", "score": 0.5, "feedback": "Lists concepts but doesn't connect them."})
        result = evaluate_free_text_response(llm, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE, "Gradient descent and learning rate are both used.")
        assert result.solo_level == "multistructural"
        assert result.score == pytest.approx(0.5)

    def test_relational_response(self):
        llm = _make_llm({"solo_level": "relational", "score": 0.75, "feedback": "Connects learning rate and update size well."})
        result = evaluate_free_text_response(llm, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE,
                                             "The learning rate controls how large each gradient descent step is.")
        assert result.solo_level == "relational"
        assert result.score == pytest.approx(0.75)

    def test_extended_abstract_response(self):
        llm = _make_llm({"solo_level": "extended_abstract", "score": 1.0, "feedback": "Excellent generalization and prediction."})
        result = evaluate_free_text_response(llm, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE,
                                             "A too-high learning rate causes divergence because updates overshoot the minimum.")
        assert result.solo_level == "extended_abstract"
        assert result.score == pytest.approx(1.0)

    def test_strips_markdown_fences(self):
        mock = MagicMock()
        mock.invoke.return_value = '```json\n{"solo_level": "relational", "score": 0.75, "feedback": "Good."}\n```'
        result = evaluate_free_text_response(mock, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE, "Some answer.")
        assert result.solo_level == "relational"

    def test_message_object_content(self):
        """LLM responses may be message objects with a .content attribute."""
        mock = MagicMock()
        msg = MagicMock()
        msg.content = json.dumps({"solo_level": "unistructural", "score": 0.25, "feedback": "Basic."})
        mock.invoke.return_value = msg
        result = evaluate_free_text_response(mock, SAMPLE_QUESTION, SAMPLE_RUBRIC, SAMPLE_EXAMPLE, "Gradient descent.")
        assert result.solo_level == "unistructural"


# ---------------------------------------------------------------------------
# Tests for evaluate_short_answer_response
# ---------------------------------------------------------------------------

class TestEvaluateShortAnswerResponse:
    def test_short_answer_semantic_correct(self):
        llm = _make_llm({"is_correct": True, "feedback": "Correct meaning conveyed."})
        is_correct, feedback = evaluate_short_answer_response(llm, "What language is CPython in?", "C", "c language")
        assert is_correct is True
        assert "Correct" in feedback

    def test_short_answer_semantic_wrong(self):
        llm = _make_llm({"is_correct": False, "feedback": "Different meaning."})
        is_correct, feedback = evaluate_short_answer_response(llm, "What language is CPython in?", "C", "Java")
        assert is_correct is False

    def test_returns_tuple(self):
        llm = _make_llm({"is_correct": True, "feedback": "Good."})
        result = evaluate_short_answer_response(llm, "Q?", "Expected", "Answer")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_strips_markdown_fences(self):
        mock = MagicMock()
        mock.invoke.return_value = '```\n{"is_correct": true, "feedback": "Yes."}\n```'
        is_correct, _ = evaluate_short_answer_response(mock, "Q?", "A", "A")
        assert is_correct is True

    def test_message_object_content(self):
        mock = MagicMock()
        msg = MagicMock()
        msg.content = json.dumps({"is_correct": False, "feedback": "Nope."})
        mock.invoke.return_value = msg
        is_correct, _ = evaluate_short_answer_response(mock, "Q?", "A", "B")
        assert is_correct is False
