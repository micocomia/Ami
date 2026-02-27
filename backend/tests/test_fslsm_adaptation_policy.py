"""Tests for deterministic FSLSM adaptation policy updates."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learner_profiler.utils.fslsm_adaptation import update_fslsm_from_evidence


def _profile(*, processing=0.0, perception=0.0, input_dim=0.0, understanding=0.0):
    return {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": processing,
                "fslsm_perception": perception,
                "fslsm_input": input_dim,
                "fslsm_understanding": understanding,
            }
        }
    }


def _events(severe=False, success=False):
    return [
        {"severe_failure": severe, "strong_success": success},
        {"severe_failure": severe, "strong_success": success},
        {"severe_failure": False, "strong_success": False},
    ]


class TestFslsmAdaptationPolicy:
    def test_strong_success_on_negative_key_reinforces_negative_direction(self):
        profile = _profile(processing=-0.70)
        state = {
            "evidence_windows": {
                "fslsm_processing:negative": _events(severe=False, success=True),
            },
            "daily_movement_budget": {},
        }

        updated, changes = update_fslsm_from_evidence(profile, state, daily_cap=0.20)

        assert changes["fslsm_processing"] == -0.05
        assert updated["learning_preferences"]["fslsm_dimensions"]["fslsm_processing"] == -0.75

    def test_strong_success_on_positive_key_reinforces_positive_direction(self):
        profile = _profile(perception=0.40)
        state = {
            "evidence_windows": {
                "fslsm_perception:positive": _events(severe=False, success=True),
            },
            "daily_movement_budget": {},
        }

        updated, changes = update_fslsm_from_evidence(profile, state, daily_cap=0.20)

        assert changes["fslsm_perception"] == 0.05
        assert updated["learning_preferences"]["fslsm_dimensions"]["fslsm_perception"] == 0.45

    def test_severe_failure_moves_away_from_signaled_style(self):
        profile = _profile(input_dim=-0.50, understanding=0.50)
        state = {
            "evidence_windows": {
                "fslsm_input:negative": _events(severe=True, success=False),
                "fslsm_understanding:positive": _events(severe=True, success=False),
            },
            "daily_movement_budget": {},
        }

        updated, changes = update_fslsm_from_evidence(profile, state, daily_cap=0.20)

        assert changes["fslsm_input"] == 0.10
        assert changes["fslsm_understanding"] == -0.10
        assert updated["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] == -0.4
        assert updated["learning_preferences"]["fslsm_dimensions"]["fslsm_understanding"] == 0.4
