"""Tests for the GET /behavioral-metrics/{user_id} endpoint.

Run from the repo root:
    python -m pytest backend/tests/test_behavioral_metrics.py -v
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point store module at a temp directory and reset in-memory state."""
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_USER_STATES_PATH", data_dir / "user_states.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_user_states", {})


@pytest.fixture()
def client(_isolate_store):
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


class TestBehavioralMetrics:

    def test_no_state_returns_404(self, client):
        resp = client.get("/behavioral-metrics/unknown_user")
        assert resp.status_code == 404

    def test_empty_state_returns_zeros(self, client):
        client.put("/user-state/alice", json={"state": {}})
        resp = client.get("/behavioral-metrics/alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_completed"] == 0
        assert data["avg_session_duration_sec"] == 0.0
        assert data["total_learning_time_sec"] == 0.0
        assert data["motivational_triggers_count"] == 0
        assert data["mastery_history"] == []
        assert data["latest_mastery_rate"] is None

    def test_completed_sessions_computed(self, client):
        state = {
            "session_learning_times": {
                "0-0": {"start_time": 1000.0, "end_time": 2800.0, "trigger_time_list": [1000.0]},
                "0-1": {"start_time": 3000.0, "end_time": 4200.0, "trigger_time_list": [3000.0]},
            }
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["sessions_completed"] == 2
        assert data["total_learning_time_sec"] == 3000.0  # 1800 + 1200
        assert data["avg_session_duration_sec"] == 1500.0  # 3000 / 2

    def test_goal_filter(self, client):
        state = {
            "session_learning_times": {
                "0-0": {"start_time": 1000.0, "end_time": 2000.0, "trigger_time_list": [1000.0]},
                "1-0": {"start_time": 3000.0, "end_time": 4000.0, "trigger_time_list": [3000.0]},
            }
        }
        client.put("/user-state/alice", json={"state": state})
        # Goal 0 only
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        assert resp.json()["sessions_completed"] == 1
        # Goal 1 only
        resp = client.get("/behavioral-metrics/alice?goal_id=1")
        assert resp.json()["sessions_completed"] == 1

    def test_trigger_count(self, client):
        state = {
            "session_learning_times": {
                "0-0": {
                    "start_time": 1000.0,
                    "end_time": 2000.0,
                    "trigger_time_list": [1000.0, 1180.0, 1360.0],  # 2 actual triggers
                },
            }
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        assert resp.json()["motivational_triggers_count"] == 2

    def test_mastery_history(self, client):
        state = {
            "learned_skills_history": {"0": [0.0, 0.25, 0.5]},
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["mastery_history"] == [0.0, 0.25, 0.5]
        assert data["latest_mastery_rate"] == 0.5

    def test_sessions_learned_count(self, client):
        state = {
            "goals": [
                {
                    "id": 0,
                    "learning_path": [
                        {"if_learned": True},
                        {"if_learned": False},
                        {"if_learned": True},
                    ],
                }
            ],
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["total_sessions_in_path"] == 3
        assert data["sessions_learned"] == 2
