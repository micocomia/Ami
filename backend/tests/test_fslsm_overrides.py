"""Tests for deterministic FSLSM structural overrides."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learning_plan_generator.agents.learning_path_scheduler import (
    apply_fslsm_structural_overrides,
)


def _profile(*, processing=0.0, perception=0.0, understanding=0.0):
    return {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": processing,
                "fslsm_perception": perception,
                "fslsm_understanding": understanding,
            }
        }
    }


def _session(name: str, *, learned: bool = False, sequence_hint=None):
    return {
        "id": name,
        "title": name,
        "abstract": f"{name} abstract",
        "if_learned": learned,
        "associated_skills": ["Skill A"],
        "desired_outcome_when_completed": [{"name": "Skill A", "level": "beginner"}],
        "has_checkpoint_challenges": False,
        "thinking_time_buffer_minutes": 0,
        "session_sequence_hint": sequence_hint,
        "navigation_mode": "linear",
    }


class TestFSLSMStructuralOverrides:

    def test_intuitive_perception_forces_theory_first(self):
        sessions = [_session("Session 1", sequence_hint="application-first")]

        result = apply_fslsm_structural_overrides(
            sessions,
            _profile(perception=1.0),
        )

        assert result[0]["session_sequence_hint"] == "theory-first"

    def test_balanced_perception_clears_stale_sequence_hint(self):
        sessions = [_session("Session 1", sequence_hint="application-first")]

        result = apply_fslsm_structural_overrides(
            sessions,
            _profile(perception=0.0),
        )

        assert result[0]["session_sequence_hint"] is None

    def test_reschedule_preserves_learned_sessions(self):
        sessions = [
            _session("Session 1", learned=True, sequence_hint="application-first"),
            _session("Session 2", learned=False, sequence_hint="application-first"),
        ]

        result = apply_fslsm_structural_overrides(
            sessions,
            _profile(perception=1.0),
            preserve_learned=True,
        )

        assert result[0]["session_sequence_hint"] == "application-first"
        assert result[1]["session_sequence_hint"] == "theory-first"

    def test_processing_and_understanding_fields_are_aligned(self):
        sessions = [_session("Session 1")]

        result = apply_fslsm_structural_overrides(
            sessions,
            _profile(processing=0.8, perception=-0.8, understanding=0.6),
        )

        assert result[0]["has_checkpoint_challenges"] is False
        assert result[0]["thinking_time_buffer_minutes"] == 10
        assert result[0]["session_sequence_hint"] == "application-first"
        assert result[0]["navigation_mode"] == "free"
