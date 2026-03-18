"""Tests for mastery evaluation logic.

Tests the relationship between quiz scores and mastery thresholds.

Run from the repo root:
    python -m pytest backend/tests/test_mastery_evaluation.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.content_generator.utils.quiz_scorer import compute_quiz_score, get_mastery_threshold_for_session


THRESHOLD_MAP = {
    "beginner": 60,
    "intermediate": 70,
    "advanced": 80,
    "expert": 90,
}

QUIZ_DATA = {
    "single_choice_questions": [
        {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_option": 0, "explanation": ""},
        {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_option": 1, "explanation": ""},
        {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_option": 2, "explanation": ""},
        {"question": "Q4", "options": ["A", "B", "C", "D"], "correct_option": 3, "explanation": ""},
        {"question": "Q5", "options": ["A", "B", "C", "D"], "correct_option": 0, "explanation": ""},
    ],
    "multiple_choice_questions": [
        {"question": "Q6", "options": ["A", "B", "C"], "correct_options": [0, 1], "explanation": ""},
    ],
    "true_false_questions": [
        {"question": "Q7", "options": [], "correct_answer": True, "explanation": ""},
    ],
    "short_answer_questions": [
        {"question": "Q8", "expected_answer": "Python", "explanation": ""},
        {"question": "Q9", "expected_answer": "Java", "explanation": ""},
        {"question": "Q10", "expected_answer": "C", "explanation": ""},
    ],
}


def _get_score(answers):
    """Helper to compute score percentage."""
    _, _, pct = compute_quiz_score(QUIZ_DATA, answers)
    return pct


def _is_mastered(score_pct, session_proficiency):
    """Helper: check if score meets mastery threshold for given proficiency."""
    session = {
        "desired_outcome_when_completed": [
            {"name": "Skill", "level": session_proficiency}
        ]
    }
    threshold = get_mastery_threshold_for_session(session, THRESHOLD_MAP)
    return score_pct >= threshold


class TestMasteryEvaluation:
    def test_mastery_pass(self):
        """Score above threshold should be mastered."""
        # 8/10 correct = 80%, intermediate threshold = 70%
        answers = {
            "single_choice_questions": ["A", "B", "C", "D", "A"],  # 5/5
            "multiple_choice_questions": [["A", "B"]],              # 1/1
            "true_false_questions": ["True"],                        # 1/1
            "short_answer_questions": ["Python", "wrong", "wrong"], # 1/3
        }
        score = _get_score(answers)
        assert score == 80.0
        assert _is_mastered(score, "intermediate") is True  # 80 >= 70

    def test_mastery_fail(self):
        """Score below threshold should not be mastered."""
        # 3/10 = 30%
        answers = {
            "single_choice_questions": ["A", "wrong", "wrong", "wrong", "wrong"],
            "multiple_choice_questions": [["A", "B"]],
            "true_false_questions": ["False"],
            "short_answer_questions": ["Python", "wrong", "wrong"],
        }
        score = _get_score(answers)
        assert score == 30.0
        assert _is_mastered(score, "intermediate") is False  # 30 < 70

    def test_threshold_boundary_pass(self):
        """Score exactly at threshold should be mastered."""
        # 7/10 = 70%, intermediate threshold = 70%
        answers = {
            "single_choice_questions": ["A", "B", "C", "D", "A"],  # 5/5
            "multiple_choice_questions": [["A", "B"]],              # 1/1
            "true_false_questions": ["True"],                        # 1/1
            "short_answer_questions": ["wrong", "wrong", "wrong"], # 0/3
        }
        score = _get_score(answers)
        assert score == 70.0
        assert _is_mastered(score, "intermediate") is True  # 70 >= 70

    def test_proficiency_based_threshold_beginner(self):
        """Beginner session uses 60% threshold — easier to master."""
        # 6/10 = 60%
        answers = {
            "single_choice_questions": ["A", "B", "C", "wrong", "wrong"],  # 3/5
            "multiple_choice_questions": [["A", "B"]],                      # 1/1
            "true_false_questions": ["True"],                                # 1/1
            "short_answer_questions": ["Python", "wrong", "wrong"],         # 1/3
        }
        score = _get_score(answers)
        assert score == 60.0
        assert _is_mastered(score, "beginner") is True      # 60 >= 60
        assert _is_mastered(score, "intermediate") is False  # 60 < 70

    def test_proficiency_based_threshold_expert(self):
        """Expert session uses 90% threshold — harder to master."""
        answers = {
            "single_choice_questions": ["A", "B", "C", "D", "A"],  # 5/5
            "multiple_choice_questions": [["A", "B"]],              # 1/1
            "true_false_questions": ["True"],                        # 1/1
            "short_answer_questions": ["Python", "Java", "wrong"], # 2/3
        }
        score = _get_score(answers)
        assert score == 90.0
        assert _is_mastered(score, "expert") is True       # 90 >= 90
        assert _is_mastered(score, "advanced") is True     # 90 >= 80

    def test_threshold_lookup_missing_level_uses_default(self):
        """Unknown proficiency level is skipped; falls back to lowest (beginner)."""
        session = {
            "desired_outcome_when_completed": [
                {"name": "Skill", "level": "unknown_level"}
            ]
        }
        threshold = get_mastery_threshold_for_session(session, THRESHOLD_MAP, default=70)
        # "unknown_level" is not recognized, so highest_idx stays at 0 -> beginner -> 60
        assert threshold == 60

    def test_empty_outcomes_falls_back_to_default(self):
        """Session with no outcomes uses the default threshold."""
        session = {"desired_outcome_when_completed": []}
        threshold = get_mastery_threshold_for_session(session, THRESHOLD_MAP, default=75)
        assert threshold == 75
