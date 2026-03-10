"""Tests for utils/motivational_messages.py and the heartbeat trigger integration.

Run from the repo root:
    python -m pytest backend/tests/test_motivational_messages.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from utils.motivational_messages import (
    _ENCOURAGEMENT_DIM_ORDER,
    _ENCOURAGEMENT_MESSAGES,
    _POSTURE_MESSAGES,
    pick_motivational_message,
)
from utils import store


# ---------------------------------------------------------------------------
# Unit tests — pure function, no I/O
# ---------------------------------------------------------------------------

class TestPostureMessages:
    def test_posture_rotates_across_all_three_variants(self):
        seen = set()
        for i in range(6):
            msg = pick_motivational_message("posture", {}, trigger_index=i)
            seen.add(msg)
        assert len(seen) == len(_POSTURE_MESSAGES)

    def test_posture_cycles_deterministically(self):
        for i in range(9):
            expected = _POSTURE_MESSAGES[i % len(_POSTURE_MESSAGES)]
            assert pick_motivational_message("posture", {}, trigger_index=i) == expected

    def test_posture_ignores_fslsm_dims(self):
        msg_empty = pick_motivational_message("posture", {}, trigger_index=0)
        msg_dims = pick_motivational_message(
            "posture",
            {"fslsm_processing": -0.9, "fslsm_perception": 0.9},
            trigger_index=0,
        )
        assert msg_empty == msg_dims


class TestEncouragementDimensionCycling:
    def test_cycles_through_all_four_dimensions_in_order(self):
        # With neutral dims (all 0), every message is distinct per dimension
        neutral = {k: 0.0 for k in _ENCOURAGEMENT_DIM_ORDER}
        msgs = [
            pick_motivational_message("encouragement", neutral, trigger_index=i)
            for i in range(len(_ENCOURAGEMENT_DIM_ORDER))
        ]
        # Should yield a message from each dimension — all distinct for neutral band
        assert len(msgs) == 4
        # Each maps to the first neutral variant of its dimension
        for i, dim in enumerate(_ENCOURAGEMENT_DIM_ORDER):
            expected = _ENCOURAGEMENT_MESSAGES[dim]["neutral"][0]
            assert msgs[i] == expected, f"dim={dim} index={i}"

    def test_variant_alternates_on_second_pass(self):
        neutral = {k: 0.0 for k in _ENCOURAGEMENT_DIM_ORDER}
        n = len(_ENCOURAGEMENT_DIM_ORDER)
        for i, dim in enumerate(_ENCOURAGEMENT_DIM_ORDER):
            first_pass = pick_motivational_message("encouragement", neutral, trigger_index=i)
            second_pass = pick_motivational_message("encouragement", neutral, trigger_index=i + n)
            assert first_pass == _ENCOURAGEMENT_MESSAGES[dim]["neutral"][0]
            assert second_pass == _ENCOURAGEMENT_MESSAGES[dim]["neutral"][1]
            assert first_pass != second_pass


class TestBandClassification:
    def test_low_band_active_processing(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": -0.8},
            trigger_index=0,  # fslsm_processing dimension
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["low"]

    def test_high_band_reflective_processing(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": 0.8},
            trigger_index=0,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["high"]

    def test_low_band_sensing_perception(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_perception": -0.9},
            trigger_index=1,  # fslsm_perception dimension
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_perception"]["low"]

    def test_high_band_intuitive_perception(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_perception": 0.9},
            trigger_index=1,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_perception"]["high"]

    def test_low_band_visual_input(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_input": -0.5},
            trigger_index=2,  # fslsm_input dimension
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_input"]["low"]

    def test_high_band_verbal_input(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_input": 0.5},
            trigger_index=2,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_input"]["high"]

    def test_low_band_sequential_understanding(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_understanding": -0.5},
            trigger_index=3,  # fslsm_understanding dimension
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_understanding"]["low"]

    def test_high_band_global_understanding(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_understanding": 0.5},
            trigger_index=3,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_understanding"]["high"]


class TestBoundaryScores:
    """Boundary values -0.3 and +0.3 must be classified as neutral (strict inequalities)."""

    def test_exactly_minus_0_3_is_neutral(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": -0.3},
            trigger_index=0,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["neutral"]

    def test_exactly_plus_0_3_is_neutral(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": 0.3},
            trigger_index=0,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["neutral"]

    def test_just_below_minus_0_3_is_low(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": -0.31},
            trigger_index=0,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["low"]

    def test_just_above_plus_0_3_is_high(self):
        msg = pick_motivational_message(
            "encouragement",
            {"fslsm_processing": 0.31},
            trigger_index=0,
        )
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["high"]


class TestEdgeCases:
    def test_empty_dict_falls_back_to_neutral(self):
        msg = pick_motivational_message("encouragement", {}, trigger_index=0)
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["neutral"]

    def test_none_dims_falls_back_to_neutral(self):
        msg = pick_motivational_message("encouragement", None, trigger_index=0)
        assert msg in _ENCOURAGEMENT_MESSAGES["fslsm_processing"]["neutral"]

    def test_none_and_empty_produce_same_result(self):
        assert (
            pick_motivational_message("encouragement", None, trigger_index=0)
            == pick_motivational_message("encouragement", {}, trigger_index=0)
        )

    def test_large_trigger_index_does_not_overflow(self):
        # Should not raise; modulo arithmetic keeps it in range
        msg = pick_motivational_message("encouragement", {}, trigger_index=10_000)
        assert isinstance(msg, str) and len(msg) > 0

    def test_large_posture_trigger_index(self):
        msg = pick_motivational_message("posture", {}, trigger_index=10_000)
        assert isinstance(msg, str) and len(msg) > 0


# ---------------------------------------------------------------------------
# Integration tests — heartbeat endpoint via TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _create_goal(user_id: str) -> dict:
    return store.create_goal(user_id, {"learning_goal": "Learn Python", "learning_path": []})


def _heartbeat(client, user_id: str, goal_id: int, session_index: int, event_time: str) -> dict:
    resp = client.post("/v1/session-activity", json={
        "user_id": user_id,
        "goal_id": goal_id,
        "session_index": session_index,
        "event_type": "heartbeat",
        "event_time": event_time,
    })
    assert resp.status_code == 200
    return resp.json()


class TestHeartbeatTriggerIntegration:
    def test_heartbeat_without_profile_returns_valid_shape(self, client):
        goal = _create_goal("alice")
        # Start the session first so heartbeat is accepted
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "start",
            "event_time": "2026-01-01T00:00:00+00:00",
        })
        data = _heartbeat(client, "alice", goal["id"], 0, "2026-01-01T00:03:00+00:00")
        assert "ok" in data
        trigger = data.get("trigger", {})
        assert trigger.get("show") is True
        assert trigger.get("kind") in ("posture", "encouragement")
        assert isinstance(trigger.get("message"), str)
        assert len(trigger["message"]) > 0

    def test_heartbeat_with_active_learner_returns_active_processing_message(self, client):
        goal = _create_goal("alice")
        # Seed a profile with strongly active processing (score = -0.8)
        store.upsert_profile("alice", goal["id"], {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": -0.8,
                }
            }
        })
        # Start the session
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "start",
            "event_time": "2026-01-01T00:00:00+00:00",
        })
        # First heartbeat → trigger_count=0 → posture (even index)
        _heartbeat(client, "alice", goal["id"], 0, "2026-01-01T00:03:00+00:00")
        # Second heartbeat → trigger_count=1 → encouragement (odd index)
        data = _heartbeat(client, "alice", goal["id"], 0, "2026-01-01T00:06:00+00:00")
        trigger = data.get("trigger", {})
        assert trigger.get("kind") == "encouragement"
        msg = trigger.get("message", "")
        # Active processing messages mention "applying" or "explain"
        assert "applying" in msg.lower() or "explain" in msg.lower(), (
            f"Expected active-processing message, got: {msg!r}"
        )

    def test_response_schema_is_unchanged(self, client):
        goal = _create_goal("alice")
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "start",
            "event_time": "2026-01-01T00:00:00+00:00",
        })
        data = _heartbeat(client, "alice", goal["id"], 0, "2026-01-01T00:03:00+00:00")
        assert set(data.keys()) >= {"ok", "trigger"}
        trigger = data["trigger"]
        assert "show" in trigger
        assert "kind" in trigger
        assert "message" in trigger
