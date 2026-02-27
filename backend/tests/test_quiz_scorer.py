"""Tests for the quiz scoring utility.

Run from the repo root:
    python -m pytest backend/tests/test_quiz_scorer.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils.quiz_scorer import (
    compute_quiz_score,
    get_mastery_threshold_for_session,
    get_quiz_mix_for_session,
    is_strong_success,
)


# ── Sample quiz data ──────────────────────────────────────────────────────────

SAMPLE_QUIZ_DATA = {
    "single_choice_questions": [
        {
            "question": "What is 2+2?",
            "options": ["3", "4", "5", "6"],
            "correct_option": 1,
            "explanation": "Basic arithmetic.",
        },
        {
            "question": "Capital of France?",
            "options": ["Berlin", "Madrid", "Paris", "Rome"],
            "correct_option": 2,
            "explanation": "Geography.",
        },
    ],
    "multiple_choice_questions": [
        {
            "question": "Which are prime?",
            "options": ["2", "4", "5", "9"],
            "correct_options": [0, 2],
            "explanation": "2 and 5 are prime.",
        },
    ],
    "true_false_questions": [
        {
            "question": "The earth is flat.",
            "correct_answer": False,
            "explanation": "The earth is roughly spherical.",
        },
    ],
    "short_answer_questions": [
        {
            "question": "What language is CPython written in?",
            "expected_answer": "C",
            "explanation": "CPython is the reference implementation written in C.",
        },
    ],
}


class TestComputeQuizScore:
    def test_perfect_score(self):
        answers = {
            "single_choice_questions": ["4", "Paris"],
            "multiple_choice_questions": [["2", "5"]],
            "true_false_questions": ["False"],
            "short_answer_questions": ["C"],
        }
        correct, total, pct = compute_quiz_score(SAMPLE_QUIZ_DATA, answers)
        assert total == 5
        assert correct == 5
        assert pct == 100.0

    def test_zero_score(self):
        answers = {
            "single_choice_questions": ["3", "Berlin"],
            "multiple_choice_questions": [["4", "9"]],
            "true_false_questions": ["True"],
            "short_answer_questions": ["Java"],
        }
        correct, total, pct = compute_quiz_score(SAMPLE_QUIZ_DATA, answers)
        assert total == 5
        assert correct == 0
        assert pct == 0.0

    def test_partial_score(self):
        answers = {
            "single_choice_questions": ["4", "Berlin"],  # 1 correct, 1 wrong
            "multiple_choice_questions": [["2", "5"]],    # correct
            "true_false_questions": ["True"],              # wrong
            "short_answer_questions": ["C"],               # correct
        }
        correct, total, pct = compute_quiz_score(SAMPLE_QUIZ_DATA, answers)
        assert total == 5
        assert correct == 3
        assert pct == pytest.approx(60.0)

    def test_empty_answers(self):
        answers = {}
        correct, total, pct = compute_quiz_score(SAMPLE_QUIZ_DATA, answers)
        assert total == 5
        assert correct == 0
        assert pct == 0.0

    def test_none_answers_skipped(self):
        answers = {
            "single_choice_questions": [None, "Paris"],
            "multiple_choice_questions": [None],
            "true_false_questions": [None],
            "short_answer_questions": [None],
        }
        correct, total, pct = compute_quiz_score(SAMPLE_QUIZ_DATA, answers)
        assert total == 5
        assert correct == 1  # Only "Paris" is correct

    def test_single_choice_scoring(self):
        quiz = {
            "single_choice_questions": [
                {"question": "Q", "options": ["A", "B", "C"], "correct_option": 0, "explanation": ""},
            ],
        }
        correct_ans = {"single_choice_questions": ["A"]}
        wrong_ans = {"single_choice_questions": ["B"]}
        assert compute_quiz_score(quiz, correct_ans)[0] == 1
        assert compute_quiz_score(quiz, wrong_ans)[0] == 0

    def test_multiple_choice_scoring(self):
        quiz = {
            "multiple_choice_questions": [
                {"question": "Q", "options": ["A", "B", "C"], "correct_options": [0, 2], "explanation": ""},
            ],
        }
        # Exact set match required
        assert compute_quiz_score(quiz, {"multiple_choice_questions": [["A", "C"]]})[0] == 1
        assert compute_quiz_score(quiz, {"multiple_choice_questions": [["A"]]})[0] == 0
        assert compute_quiz_score(quiz, {"multiple_choice_questions": [["A", "B", "C"]]})[0] == 0

    def test_true_false_scoring(self):
        quiz = {
            "true_false_questions": [
                {"question": "Q", "correct_answer": True, "explanation": ""},
            ],
        }
        assert compute_quiz_score(quiz, {"true_false_questions": ["True"]})[0] == 1
        assert compute_quiz_score(quiz, {"true_false_questions": ["False"]})[0] == 0

    def test_short_answer_case_insensitive(self):
        quiz = {
            "short_answer_questions": [
                {"question": "Q", "expected_answer": "Python", "explanation": ""},
            ],
        }
        assert compute_quiz_score(quiz, {"short_answer_questions": ["python"]})[0] == 1
        assert compute_quiz_score(quiz, {"short_answer_questions": ["  PYTHON  "]})[0] == 1
        assert compute_quiz_score(quiz, {"short_answer_questions": ["java"]})[0] == 0

    def test_empty_quiz_data(self):
        correct, total, pct = compute_quiz_score({}, {})
        assert total == 0
        assert correct == 0
        assert pct == 0.0


class TestComputeQuizScoreWithLLMEvaluations:
    """Tests for hybrid scoring with LLM evaluations."""

    OPEN_ENDED_QUIZ = {
        "open_ended_questions": [
            {"question": "Explain X.", "rubric": "...", "example_answer": "..."},
            {"question": "Synthesize Y.", "rubric": "...", "example_answer": "..."},
        ],
    }

    MIXED_QUIZ = {
        "single_choice_questions": [
            {"question": "Q1", "options": ["A", "B", "C"], "correct_option": 0, "explanation": ""},
        ],
        "short_answer_questions": [
            {"question": "Q2", "expected_answer": "Python", "explanation": ""},
        ],
        "open_ended_questions": [
            {"question": "Q3", "rubric": "...", "example_answer": "..."},
        ],
    }

    def test_open_ended_scoring_with_evaluations(self):
        """Open-ended fractional scores contribute to total."""
        quiz = self.OPEN_ENDED_QUIZ
        answers = {"open_ended_questions": ["Some answer.", "Another answer."]}
        evals = {
            "open_ended_evaluations": [
                {"solo_level": "relational", "score": 0.75, "feedback": "Good."},
                {"solo_level": "extended_abstract", "score": 1.0, "feedback": "Excellent."},
            ]
        }
        correct, total, pct = compute_quiz_score(quiz, answers, evals)
        assert total == 2
        assert correct == pytest.approx(1.75)
        assert pct == pytest.approx(87.5)

    def test_short_answer_with_llm_evaluation(self):
        """LLM-evaluated short answer overrides exact match."""
        quiz = {
            "short_answer_questions": [
                {"question": "Q", "expected_answer": "Python", "explanation": ""},
            ],
        }
        # Student writes "python language" which doesn't match exactly but LLM says correct
        answers = {"short_answer_questions": ["python language"]}
        evals = {"short_answer_evaluations": [{"is_correct": True, "feedback": "Correct meaning."}]}
        correct, total, pct = compute_quiz_score(quiz, answers, evals)
        assert correct == pytest.approx(1)
        assert pct == pytest.approx(100.0)

    def test_backward_compat_no_llm_evaluations(self):
        """None llm_evaluations falls back to exact string match for short answers."""
        quiz = {
            "short_answer_questions": [
                {"question": "Q", "expected_answer": "Python", "explanation": ""},
            ],
        }
        correct_ans = {"short_answer_questions": ["python"]}
        wrong_ans = {"short_answer_questions": ["java"]}
        c1, _, _ = compute_quiz_score(quiz, correct_ans, None)
        c2, _, _ = compute_quiz_score(quiz, wrong_ans, None)
        assert c1 == pytest.approx(1)
        assert c2 == pytest.approx(0)

    def test_mixed_types_with_open_ended(self):
        """All 5 types scored together correctly."""
        quiz = self.MIXED_QUIZ
        answers = {
            "single_choice_questions": ["A"],   # correct
            "short_answer_questions": ["Python"],  # correct via LLM eval
            "open_ended_questions": ["Some synthesis."],  # 0.75 score
        }
        evals = {
            "short_answer_evaluations": [{"is_correct": True, "feedback": "Correct."}],
            "open_ended_evaluations": [{"solo_level": "relational", "score": 0.75, "feedback": "Good."}],
        }
        correct, total, pct = compute_quiz_score(quiz, answers, evals)
        assert total == 3
        assert correct == pytest.approx(2.75)
        assert pct == pytest.approx(2.75 / 3 * 100)

    def test_open_ended_no_answer_scores_zero(self):
        """Missing open-ended answer contributes 0 to score."""
        quiz = self.OPEN_ENDED_QUIZ
        answers = {"open_ended_questions": [None, None]}
        evals = {
            "open_ended_evaluations": [
                {"solo_level": "relational", "score": 0.75, "feedback": "Good."},
                {"solo_level": "relational", "score": 0.75, "feedback": "Good."},
            ]
        }
        correct, total, pct = compute_quiz_score(quiz, answers, evals)
        assert total == 2
        assert correct == pytest.approx(0.0)
        assert pct == pytest.approx(0.0)

    def test_open_ended_skipped_when_no_llm_evals(self):
        """Open-ended questions with no evals still count toward total but score 0."""
        quiz = self.OPEN_ENDED_QUIZ
        answers = {"open_ended_questions": ["An answer.", "Another."]}
        correct, total, pct = compute_quiz_score(quiz, answers, None)
        assert total == 2
        assert correct == pytest.approx(0.0)


class TestGetMasteryThreshold:
    THRESHOLD_MAP = {"beginner": 60, "intermediate": 70, "advanced": 80, "expert": 90}

    def test_beginner_session(self):
        session = {
            "desired_outcome_when_completed": [
                {"name": "Skill A", "level": "beginner"},
            ]
        }
        assert get_mastery_threshold_for_session(session, self.THRESHOLD_MAP) == 60

    def test_expert_session(self):
        session = {
            "desired_outcome_when_completed": [
                {"name": "Skill A", "level": "expert"},
            ]
        }
        assert get_mastery_threshold_for_session(session, self.THRESHOLD_MAP) == 90

    def test_mixed_proficiency_uses_highest(self):
        session = {
            "desired_outcome_when_completed": [
                {"name": "Skill A", "level": "beginner"},
                {"name": "Skill B", "level": "advanced"},
            ]
        }
        assert get_mastery_threshold_for_session(session, self.THRESHOLD_MAP) == 80

    def test_empty_outcomes_uses_default(self):
        session = {"desired_outcome_when_completed": []}
        assert get_mastery_threshold_for_session(session, self.THRESHOLD_MAP, default=70) == 70

    def test_no_outcomes_key_uses_default(self):
        session = {}
        assert get_mastery_threshold_for_session(session, self.THRESHOLD_MAP, default=75) == 75


class TestStrongSuccess:
    def test_standard_margin(self):
        assert is_strong_success(70.0, 60.0) is True
        assert is_strong_success(69.9, 60.0) is False

    def test_caps_margin_target_at_max_score(self):
        assert is_strong_success(100.0, 95.0) is True
        assert is_strong_success(99.0, 95.0) is False

    def test_requires_mastery(self):
        assert is_strong_success(59.0, 60.0) is False
