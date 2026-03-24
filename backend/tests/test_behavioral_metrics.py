"""Tests for the GET /behavioral-metrics/{user_id} endpoint.

Run from the repo root:
    python -m pytest backend/tests/test_behavioral_metrics.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _create_goal(user_id: str, learning_path=None):
    return store.create_goal(user_id, {
        "learning_goal": "Goal",
        "learning_path": learning_path or [],
    })


class TestBehavioralMetrics:
    def test_no_state_returns_404(self, client):
        resp = client.get("/v1/behavioral-metrics/alice")
        assert resp.status_code == 404

    def test_empty_goal_returns_zeros(self, client):
        goal = _create_goal("alice")
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_completed"] == 0
        assert data["avg_session_duration_sec"] == 0.0
        assert data["total_learning_time_sec"] == 0.0
        assert data["motivational_triggers_count"] == 0
        assert data["mastery_history"] == []
        assert data["latest_mastery_rate"] is None

    def test_completed_sessions_computed(self, client):
        goal = _create_goal("alice", [{"if_learned": True}, {"if_learned": True}])
        store.upsert_session_activity("alice", goal["id"], 0, {
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-01-01T00:30:00+00:00",
            "trigger_events": [],
        })
        store.upsert_session_activity("alice", goal["id"], 1, {
            "start_time": "2026-01-01T01:00:00+00:00",
            "end_time": "2026-01-01T01:20:00+00:00",
            "trigger_events": [],
        })
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        data = resp.json()
        assert data["sessions_completed"] == 2
        assert data["total_learning_time_sec"] == 3000.0
        assert data["avg_session_duration_sec"] == 1500.0

    def test_goal_filter(self, client):
        goal0 = _create_goal("alice", [{"if_learned": True}])
        goal1 = _create_goal("alice", [{"if_learned": True}])
        store.upsert_session_activity("alice", goal0["id"], 0, {
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-01-01T00:10:00+00:00",
            "trigger_events": [],
        })
        store.upsert_session_activity("alice", goal1["id"], 0, {
            "start_time": "2026-01-01T01:00:00+00:00",
            "end_time": "2026-01-01T01:10:00+00:00",
            "trigger_events": [],
        })
        assert client.get(f"/v1/behavioral-metrics/alice?goal_id={goal0['id']}").json()["sessions_completed"] == 1
        assert client.get(f"/v1/behavioral-metrics/alice?goal_id={goal1['id']}").json()["sessions_completed"] == 1

    def test_trigger_count(self, client):
        goal = _create_goal("alice", [{"if_learned": True}])
        store.upsert_session_activity("alice", goal["id"], 0, {
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-01-01T00:10:00+00:00",
            "trigger_events": [
                {"kind": "posture", "time": "2026-01-01T00:03:00+00:00"},
                {"kind": "encouragement", "time": "2026-01-01T00:06:00+00:00"},
            ],
        })
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        assert resp.json()["motivational_triggers_count"] == 2

    def test_mastery_history(self, client):
        goal = _create_goal("alice")
        store.append_mastery_history("alice", goal["id"], 0.0)
        store.append_mastery_history("alice", goal["id"], 0.25)
        store.append_mastery_history("alice", goal["id"], 0.5)
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        data = resp.json()
        assert data["mastery_history"] == [0.0, 0.25, 0.5]
        assert data["latest_mastery_rate"] == 0.5

    def test_sessions_learned_count(self, client):
        goal = _create_goal("alice", [
            {"if_learned": True},
            {"if_learned": False},
            {"if_learned": True},
        ])
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        data = resp.json()
        assert data["total_sessions_in_path"] == 3
        assert data["sessions_learned"] == 2

    def test_idle_gap_not_counted_when_interval_closed_late(self, client):
        goal = _create_goal("alice", [{"if_learned": True}])
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "start",
            "event_time": "2026-01-01T00:00:00+00:00",
        })
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "heartbeat",
            "event_time": "2026-01-01T00:01:00+00:00",
        })
        client.post("/v1/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "end",
            "event_time": "2026-01-01T00:30:00+00:00",
        })
        resp = client.get(f"/v1/behavioral-metrics/alice?goal_id={goal['id']}")
        data = resp.json()
        assert data["sessions_completed"] == 1
        assert data["total_learning_time_sec"] == 60.0
