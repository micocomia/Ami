"""Endpoint tests for learner profile edit flows."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import auth_store, store


def _profile(info: str) -> dict:
    return {
        "learner_information": info,
        "learning_goal": "Learn Data Science",
        "goal_display_name": "Data Science",
        "cognitive_status": {
            "overall_progress": 30,
            "mastered_skills": [{"name": "Python Basics", "proficiency_level": "advanced"}],
            "in_progress_skills": [
                {
                    "name": "Machine Learning",
                    "required_proficiency_level": "advanced",
                    "current_proficiency_level": "beginner",
                }
            ],
        },
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_input": 0.0,
                "fslsm_understanding": 0.0,
            },
            "additional_notes": "",
        },
        "behavioral_patterns": {
            "system_usage_frequency": "daily",
            "session_duration_engagement": "30 mins",
            "motivational_triggers": "",
            "additional_notes": "",
        },
    }


def _seed_goal_and_profile(user_id: str, goal_payload: dict, profile: dict) -> int:
    goal = store.create_goal(user_id, goal_payload)
    gid = int(goal["id"])
    store.upsert_profile(user_id, gid, profile)
    return gid


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_PROFILE_SNAPSHOTS_PATH", data_dir / "profile_snapshots.json")
    monkeypatch.setattr(store, "_GOALS_PATH", data_dir / "goals.json")
    monkeypatch.setattr(store, "_LEARNING_CONTENT_PATH", data_dir / "learning_content.json")
    monkeypatch.setattr(store, "_SESSION_ACTIVITY_PATH", data_dir / "session_activity.json")
    monkeypatch.setattr(store, "_MASTERY_HISTORY_PATH", data_dir / "mastery_history.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_profile_snapshots", {})
    monkeypatch.setattr(store, "_goals", {})
    monkeypatch.setattr(store, "_learning_content_cache", {})
    monkeypatch.setattr(store, "_session_activity", {})
    monkeypatch.setattr(store, "_mastery_history", {})


@pytest.fixture(autouse=True)
def _isolate_auth_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "auth_data"
    data_dir.mkdir()
    monkeypatch.setattr(auth_store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(auth_store, "_USERS_PATH", data_dir / "users.json")
    monkeypatch.setattr(auth_store, "_users", {})


@pytest.fixture()
def client():
    from main import app

    return TestClient(app)


@patch("main.update_learning_preferences_with_llm")
@patch("main.get_llm")
def test_update_learning_preferences_slider_override_applies_explicit_dims(mock_get_llm, mock_update, client):
    user_id = "alice"
    initial_profile = _profile("info")
    goal_id = _seed_goal_and_profile(user_id, {"learning_goal": "Goal A", "learning_path": []}, initial_profile)
    mock_get_llm.return_value = MagicMock()

    llm_output = _profile("info")
    llm_output["learning_preferences"]["fslsm_dimensions"] = {
        "fslsm_processing": 0.8,
        "fslsm_perception": 0.8,
        "fslsm_input": 0.8,
        "fslsm_understanding": 0.8,
    }
    mock_update.return_value = llm_output

    response = client.post(
        "/v1/update-learning-preferences",
        json={
            "learner_profile": str(initial_profile),
            "learner_interactions": str(
                {
                    "update_mode": "fslsm_slider_override",
                    "slider_values": {
                        "processing": -0.4,
                        "perception": 0.1,
                        "input": -0.8,
                        "understanding": 0.5,
                    },
                }
            ),
            "learner_information": "",
            "user_id": user_id,
            "goal_id": goal_id,
        },
    )

    assert response.status_code == 200
    dims = response.json()["learner_profile"]["learning_preferences"]["fslsm_dimensions"]
    assert dims == {
        "fslsm_processing": -0.4,
        "fslsm_perception": 0.1,
        "fslsm_input": -0.8,
        "fslsm_understanding": 0.5,
    }
    assert response.json()["learner_profile"]["learner_information"] == "info"
    mock_update.assert_not_called()


@patch("main.update_learner_information_with_llm")
@patch("main.get_llm")
def test_update_learner_information_propagates_to_all_goals(mock_get_llm, mock_update_info, client):
    user_id = "alice"
    goal_id_a = _seed_goal_and_profile(user_id, {"learning_goal": "Goal A", "learning_path": []}, _profile("old A"))
    goal_id_b = _seed_goal_and_profile(user_id, {"learning_goal": "Goal B", "learning_path": []}, _profile("old B"))
    profile_a = store.get_profile(user_id, goal_id_a)
    profile_b = store.get_profile(user_id, goal_id_b)
    profile_a["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] = -0.6
    profile_b["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] = 0.7
    store.upsert_profile(user_id, goal_id_a, profile_a)
    store.upsert_profile(user_id, goal_id_b, profile_b)

    mock_get_llm.return_value = MagicMock()
    updated = store.get_profile(user_id, goal_id_a)
    updated["learner_information"] = "new learner information"
    mock_update_info.return_value = updated

    response = client.post(
        "/v1/update-learner-information",
        json={
            "learner_profile": str(_profile("old A")),
            "edited_learner_information": "new learner information",
            "resume_text": "",
            "user_id": user_id,
            "goal_id": goal_id_a,
        },
    )

    assert response.status_code == 200
    returned_info = response.json()["learner_profile"]["learner_information"]
    assert returned_info == "new learner information"
    returned_dims = response.json()["learner_profile"]["learning_preferences"]["fslsm_dimensions"]
    assert returned_dims["fslsm_input"] == -0.6
    assert store.get_profile(user_id, goal_id_a)["learner_information"] == "new learner information"
    assert store.get_profile(user_id, goal_id_b)["learner_information"] == "new learner information"
