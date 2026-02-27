"""Tests for explicit goal/content/activity resources after /user-state removal."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_GOALS_PATH", data_dir / "goals.json")
    monkeypatch.setattr(store, "_LEARNING_CONTENT_PATH", data_dir / "learning_content.json")
    monkeypatch.setattr(store, "_SESSION_ACTIVITY_PATH", data_dir / "session_activity.json")
    monkeypatch.setattr(store, "_MASTERY_HISTORY_PATH", data_dir / "mastery_history.json")
    monkeypatch.setattr(store, "_PROFILE_SNAPSHOTS_PATH", data_dir / "profile_snapshots.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_goals", {})
    monkeypatch.setattr(store, "_learning_content_cache", {})
    monkeypatch.setattr(store, "_session_activity", {})
    monkeypatch.setattr(store, "_mastery_history", {})
    monkeypatch.setattr(store, "_profile_snapshots", {})


@pytest.fixture()
def client(_isolate_store):
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


class TestGoalResources:
    def test_user_state_endpoints_removed(self, client):
        assert client.get("/user-state/alice").status_code == 404
        assert client.put("/user-state/alice", json={"state": {}}).status_code == 404
        assert client.delete("/user-state/alice").status_code == 404

    def test_goal_crud_round_trip(self, client):
        create_resp = client.post(
            "/goals/alice",
            json={
                "learning_goal": "Learn Python",
                "skill_gaps": [],
                "learning_path": [],
                "learner_profile": {"cognitive_status": {"overall_progress": 0}},
            },
        )
        assert create_resp.status_code == 200
        goal = create_resp.json()
        assert goal["learning_goal"] == "Learn Python"

        list_resp = client.get("/goals/alice")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["goals"]) == 1

        patch_resp = client.patch(f"/goals/alice/{goal['id']}", json={"learning_goal": "Learn Python Well"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["learning_goal"] == "Learn Python Well"

        delete_resp = client.delete(f"/goals/alice/{goal['id']}")
        assert delete_resp.status_code == 200
        assert delete_resp.json() == {"ok": True}
        assert client.get("/goals/alice").json()["goals"] == []

    def test_learning_content_cache_round_trip(self, client):
        goal = store.create_goal("alice", {"learning_goal": "Learn Python", "learning_path": [{"id": "Session 1"}]})
        store.upsert_learning_content("alice", goal["id"], 0, {
            "document": "## Doc\n\nContent",
            "quizzes": {"single_choice_questions": []},
            "sources_used": [],
            "content_format": "standard",
        })

        get_resp = client.get(f"/learning-content/alice/{goal['id']}/0")
        assert get_resp.status_code == 200
        assert get_resp.json()["document"].startswith("## Doc")

        delete_resp = client.delete(f"/learning-content/alice/{goal['id']}/0")
        assert delete_resp.status_code == 200
        assert client.get(f"/learning-content/alice/{goal['id']}/0").status_code == 404

    def test_session_activity_endpoint(self, client):
        goal = store.create_goal("alice", {"learning_goal": "Learn Python", "learning_path": [{"id": "Session 1"}]})
        start_resp = client.post("/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "start",
        })
        assert start_resp.status_code == 200
        heartbeat_resp = client.post("/session-activity", json={
            "user_id": "alice",
            "goal_id": goal["id"],
            "session_index": 0,
            "event_type": "heartbeat",
            "event_time": "2026-01-01T01:00:00+00:00",
        })
        assert heartbeat_resp.status_code == 200
        assert "trigger" in heartbeat_resp.json()
