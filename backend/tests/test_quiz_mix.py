"""Tests for quiz mix utility.

Run from the repo root:
    python -m pytest backend/tests/test_quiz_mix.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils.quiz_scorer import get_quiz_mix_for_session


QUIZ_MIX_CONFIG = {
    "beginner": {
        "single_choice_count": 4,
        "multiple_choice_count": 0,
        "true_false_count": 1,
        "short_answer_count": 0,
        "open_ended_count": 0,
    },
    "intermediate": {
        "single_choice_count": 2,
        "multiple_choice_count": 2,
        "true_false_count": 1,
        "short_answer_count": 0,
        "open_ended_count": 0,
    },
    "advanced": {
        "single_choice_count": 1,
        "multiple_choice_count": 1,
        "true_false_count": 0,
        "short_answer_count": 2,
        "open_ended_count": 1,
    },
    "expert": {
        "single_choice_count": 0,
        "multiple_choice_count": 1,
        "true_false_count": 0,
        "short_answer_count": 1,
        "open_ended_count": 3,
    },
}


def _session(levels):
    return {
        "desired_outcome_when_completed": [
            {"name": f"Skill {l}", "level": l} for l in levels
        ]
    }


class TestGetQuizMixForSession:
    def test_beginner_mix(self):
        mix = get_quiz_mix_for_session(_session(["beginner"]), QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 4
        assert mix["multiple_choice_count"] == 0
        assert mix["true_false_count"] == 1
        assert mix["short_answer_count"] == 0
        assert mix["open_ended_count"] == 0

    def test_intermediate_mix(self):
        mix = get_quiz_mix_for_session(_session(["intermediate"]), QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 2
        assert mix["multiple_choice_count"] == 2
        assert mix["true_false_count"] == 1
        assert mix["short_answer_count"] == 0
        assert mix["open_ended_count"] == 0

    def test_advanced_mix(self):
        mix = get_quiz_mix_for_session(_session(["advanced"]), QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 1
        assert mix["multiple_choice_count"] == 1
        assert mix["true_false_count"] == 0
        assert mix["short_answer_count"] == 2
        assert mix["open_ended_count"] == 1

    def test_expert_mix(self):
        mix = get_quiz_mix_for_session(_session(["expert"]), QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 0
        assert mix["multiple_choice_count"] == 1
        assert mix["true_false_count"] == 0
        assert mix["short_answer_count"] == 1
        assert mix["open_ended_count"] == 3

    def test_mixed_proficiency_uses_highest(self):
        # Session with beginner + expert outcomes → expert mix
        mix = get_quiz_mix_for_session(_session(["beginner", "expert"]), QUIZ_MIX_CONFIG)
        assert mix["open_ended_count"] == 3
        assert mix["single_choice_count"] == 0

    def test_empty_outcomes_uses_beginner(self):
        # No outcomes → falls back to index 0 → beginner mix
        mix = get_quiz_mix_for_session({"desired_outcome_when_completed": []}, QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 4
        assert mix["open_ended_count"] == 0

    def test_no_outcomes_key_uses_beginner(self):
        # Missing key → falls back to beginner
        mix = get_quiz_mix_for_session({}, QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 4
        assert mix["open_ended_count"] == 0

    def test_unknown_level_skipped(self):
        # Unknown level is ignored; remains at lowest recognized level
        session = {
            "desired_outcome_when_completed": [
                {"name": "Skill", "level": "unknown_level"},
                {"name": "Skill B", "level": "intermediate"},
            ]
        }
        mix = get_quiz_mix_for_session(session, QUIZ_MIX_CONFIG)
        assert mix["single_choice_count"] == 2  # intermediate
        assert mix["multiple_choice_count"] == 2
