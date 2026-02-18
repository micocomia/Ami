"""Tests for the plan regeneration decision logic.

Run from the repo root:
    python -m pytest backend/tests/test_plan_regeneration.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.tools.plan_regeneration_tool import (
    compute_fslsm_deltas,
    count_mastery_failures,
    decide_regeneration,
)


def _make_plan(num_sessions=5, num_learned=2):
    """Helper to create a learning path with some learned sessions."""
    sessions = []
    for i in range(num_sessions):
        sessions.append({
            "id": f"Session {i+1}",
            "title": f"Session {i+1}",
            "abstract": f"Content for session {i+1}",
            "if_learned": i < num_learned,
            "associated_skills": ["Skill A"],
            "desired_outcome_when_completed": [
                {"name": "Skill A", "level": "intermediate"}
            ],
        })
    return {"learning_path": sessions}


def _make_fslsm(processing=0.0, perception=0.0, input_dim=0.0, understanding=0.0):
    """Helper to create FSLSM dimensions dict."""
    return {
        "fslsm_processing": processing,
        "fslsm_perception": perception,
        "fslsm_input": input_dim,
        "fslsm_understanding": understanding,
    }


class TestComputeFSLSMDeltas:

    def test_identical_preferences(self):
        old = _make_fslsm(0.5, -0.3, 0.1, 0.0)
        new = _make_fslsm(0.5, -0.3, 0.1, 0.0)
        deltas = compute_fslsm_deltas(old, new)
        assert all(d == 0.0 for d in deltas.values())

    def test_delta_computation(self):
        old = _make_fslsm(-0.8, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.3, 0.0, 0.0, 0.0)
        deltas = compute_fslsm_deltas(old, new)
        assert abs(deltas["fslsm_processing"] - 1.1) < 0.001

    def test_missing_dimensions_default_to_zero(self):
        old = {"fslsm_processing": 0.5}
        new = {}
        deltas = compute_fslsm_deltas(old, new)
        assert deltas["fslsm_processing"] == 0.5
        assert deltas["fslsm_perception"] == 0.0


class TestCountMasteryFailures:

    def test_no_failures(self):
        results = [
            {"is_mastered": True},
            {"is_mastered": True},
        ]
        assert count_mastery_failures(results) == 0

    def test_single_failure(self):
        results = [
            {"is_mastered": True},
            {"is_mastered": False},
            {"is_mastered": True},
        ]
        assert count_mastery_failures(results) == 1

    def test_multiple_failures(self):
        results = [
            {"is_mastered": False},
            {"is_mastered": False},
            {"is_mastered": True},
        ]
        assert count_mastery_failures(results) == 2


class TestDecideRegeneration:

    def test_keep_on_minor_preference_change(self):
        """abs delta < 0.3 on all dims AND no mastery issues = keep."""
        plan = _make_plan()
        old = _make_fslsm(0.0, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.1, -0.1, 0.2, 0.0)
        decision = decide_regeneration(plan, old, new)
        assert decision.action == "keep"
        assert len(decision.affected_sessions) == 0

    def test_adjust_future_on_moderate_change(self):
        """abs delta in [0.3, 0.5) on any dim = adjust_future."""
        plan = _make_plan()
        old = _make_fslsm(0.0, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.35, 0.0, 0.0, 0.0)
        decision = decide_regeneration(plan, old, new)
        assert decision.action == "adjust_future"
        # Only future (unlearned) sessions should be affected
        assert all(
            i >= 2 for i in decision.affected_sessions
        )

    def test_regenerate_on_major_preference_shift(self):
        """abs delta >= 0.5 on any dim = regenerate."""
        plan = _make_plan()
        old = _make_fslsm(0.0, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.6, 0.0, 0.0, 0.0)
        decision = decide_regeneration(plan, old, new)
        assert decision.action == "regenerate"

    def test_regenerate_on_sign_flip(self):
        """e.g., -0.8 → 0.3 (abs delta=1.1) = regenerate."""
        plan = _make_plan()
        old = _make_fslsm(-0.8, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.3, 0.0, 0.0, 0.0)
        decision = decide_regeneration(plan, old, new)
        assert decision.action == "regenerate"
        assert "1.10" in decision.reason

    def test_adjust_future_on_single_mastery_failure(self):
        """One session below threshold = adjust_future."""
        plan = _make_plan()
        old = _make_fslsm()
        new = _make_fslsm()
        mastery = [
            {"is_mastered": True},
            {"is_mastered": False},
        ]
        decision = decide_regeneration(plan, old, new, mastery)
        assert decision.action == "adjust_future"

    def test_regenerate_on_multiple_mastery_failures(self):
        """Multiple failures = regenerate."""
        plan = _make_plan()
        old = _make_fslsm()
        new = _make_fslsm()
        mastery = [
            {"is_mastered": False},
            {"is_mastered": False},
            {"is_mastered": True},
        ]
        decision = decide_regeneration(plan, old, new, mastery)
        assert decision.action == "regenerate"

    def test_preserves_learned_sessions(self):
        """Learned sessions should not appear in affected_sessions for adjust/regenerate."""
        plan = _make_plan(num_sessions=5, num_learned=2)
        old = _make_fslsm(0.0, 0.0, 0.0, 0.0)
        new = _make_fslsm(0.4, 0.0, 0.0, 0.0)
        decision = decide_regeneration(plan, old, new)
        assert decision.action == "adjust_future"
        # Sessions 0, 1 are learned; affected should be 2, 3, 4
        assert 0 not in decision.affected_sessions
        assert 1 not in decision.affected_sessions
        assert set(decision.affected_sessions) == {2, 3, 4}

    def test_mastery_failure_suggests_reinforcement(self):
        """Single mastery failure reason should mention reinforcement."""
        plan = _make_plan()
        old = _make_fslsm()
        new = _make_fslsm()
        mastery = [{"is_mastered": False}]
        decision = decide_regeneration(plan, old, new, mastery)
        assert "reinforcement" in decision.reason.lower()

    def test_keep_with_all_mastered(self):
        """No pref change + all mastered = keep."""
        plan = _make_plan()
        old = _make_fslsm()
        new = _make_fslsm()
        mastery = [{"is_mastered": True}, {"is_mastered": True}]
        decision = decide_regeneration(plan, old, new, mastery)
        assert decision.action == "keep"

    def test_empty_mastery_results(self):
        """Empty mastery results with no pref change = keep."""
        plan = _make_plan()
        old = _make_fslsm()
        new = _make_fslsm()
        decision = decide_regeneration(plan, old, new, [])
        assert decision.action == "keep"
