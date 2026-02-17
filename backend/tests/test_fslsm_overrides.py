"""Tests for FSLSM deterministic post-processing overrides.

Run from the repo root:
    python -m pytest backend/tests/test_fslsm_overrides.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.learning_plan_generator.agents.learning_path_scheduler import (
    _apply_fslsm_overrides,
)


def _make_profile(processing=0.0, perception=0.0, input_dim=0.0, understanding=0.0):
    """Helper to create a learner profile dict with given FSLSM dimensions."""
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


def _make_learning_path(num_sessions=3, proficiency="intermediate"):
    """Helper to create a learning path dict with N sessions."""
    sessions = []
    for i in range(num_sessions):
        sessions.append({
            "id": f"Session {i+1}",
            "title": f"Session {i+1}",
            "abstract": "Test session",
            "if_learned": False,
            "associated_skills": ["Skill A"],
            "desired_outcome_when_completed": [
                {"name": "Skill A", "level": proficiency}
            ],
        })
    return {"learning_path": sessions}


class TestFSLSMOverrides:

    def test_active_learner_gets_checkpoint_challenges(self):
        """Active (processing <= -0.3) should set has_checkpoint_challenges=True."""
        profile = _make_profile(processing=-0.7)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["has_checkpoint_challenges"] is True

    def test_reflective_learner_gets_thinking_time(self):
        """Reflective (processing >= 0.3) should set thinking_time_buffer_minutes >= 10."""
        profile = _make_profile(processing=0.7)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["thinking_time_buffer_minutes"] >= 10

    def test_sensing_gets_application_first(self):
        """Sensing (perception <= -0.3) should set session_sequence_hint='application-first'."""
        profile = _make_profile(perception=-0.5)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["session_sequence_hint"] == "application-first"

    def test_intuitive_gets_theory_first(self):
        """Intuitive (perception >= 0.3) should set session_sequence_hint='theory-first'."""
        profile = _make_profile(perception=0.5)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["session_sequence_hint"] == "theory-first"

    def test_sequential_gets_linear_nav(self):
        """Sequential (understanding <= -0.3) should set navigation_mode='linear'."""
        profile = _make_profile(understanding=-0.5)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["navigation_mode"] == "linear"

    def test_global_gets_free_nav(self):
        """Global (understanding >= 0.3) should set navigation_mode='free'."""
        profile = _make_profile(understanding=0.5)
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["navigation_mode"] == "free"

    def test_neutral_gets_defaults(self):
        """All dimensions at 0 should yield default values."""
        profile = _make_profile()
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session.get("has_checkpoint_challenges") is not True
            assert session.get("thinking_time_buffer_minutes", 0) == 0
            assert session.get("session_sequence_hint") is None
            assert session["navigation_mode"] == "linear"

    def test_overrides_apply_to_all_sessions(self):
        """All sessions in the path should be affected, not just the first."""
        profile = _make_profile(processing=-0.5, understanding=0.5)
        path = _make_learning_path(num_sessions=5)
        result = _apply_fslsm_overrides(path, profile)
        assert len(result["learning_path"]) == 5
        for session in result["learning_path"]:
            assert session["has_checkpoint_challenges"] is True
            assert session["navigation_mode"] == "free"

    def test_mastery_threshold_by_proficiency_beginner(self):
        """Beginner proficiency session should get 60% threshold."""
        profile = _make_profile()
        path = _make_learning_path(proficiency="beginner")
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["mastery_threshold"] == 60

    def test_mastery_threshold_by_proficiency_expert(self):
        """Expert proficiency session should get 90% threshold."""
        profile = _make_profile()
        path = _make_learning_path(proficiency="expert")
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["mastery_threshold"] == 90

    def test_empty_profile_uses_defaults(self):
        """Empty profile should yield default values without errors."""
        result = _apply_fslsm_overrides(_make_learning_path(), {})
        for session in result["learning_path"]:
            assert session["navigation_mode"] == "linear"

    def test_combined_dimensions(self):
        """Multiple active dimensions should all apply simultaneously."""
        profile = _make_profile(
            processing=-0.5,    # active -> checkpoint challenges
            perception=0.5,     # intuitive -> theory-first
            understanding=0.5,  # global -> free navigation
        )
        path = _make_learning_path()
        result = _apply_fslsm_overrides(path, profile)
        for session in result["learning_path"]:
            assert session["has_checkpoint_challenges"] is True
            assert session["session_sequence_hint"] == "theory-first"
            assert session["navigation_mode"] == "free"
