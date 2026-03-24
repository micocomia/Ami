"""Endpoint tests for FSLSM sign-flip evidence reset behavior."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import auth_store, store


def _profile(input_dim: float) -> dict:
    return {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_input": input_dim,
                "fslsm_understanding": 0.0,
            }
        }
    }


def _seed_goal_with_state(user_id: str, old_profile: dict) -> int:
    goal = store.create_goal(user_id, {"learning_goal": "Test goal", "learning_path": []})
    goal_id = int(goal["id"])
    store.upsert_profile(user_id, goal_id, old_profile)
    store.patch_goal(
        user_id,
        goal_id,
        {
            "adaptation_state": {
                "evidence_windows": {
                    "fslsm_input:negative": [
                        {"severe_failure": False, "strong_success": True},
                        {"severe_failure": False, "strong_success": True},
                        {"severe_failure": False, "strong_success": False},
                    ],
                    "fslsm_input:positive": [
                        {"severe_failure": False, "strong_success": True},
                    ],
                    "fslsm_perception:negative": [
                        {"severe_failure": False, "strong_success": True},
                    ],
                },
                "daily_movement_budget": {
                    "fslsm_input": {"window_start": "2026-02-27T00:00:00+00:00", "moved": 0.1},
                    "fslsm_perception": {"window_start": "2026-02-27T00:00:00+00:00", "moved": 0.1},
                },
                "last_band_state_by_dim": {},
            }
        },
    )
    return goal_id


@pytest.fixture()
def client():
    from main import app

    return TestClient(app)


@patch("main.update_learning_preferences_with_llm")
@patch("main.get_llm")
def test_update_learning_preferences_clears_only_old_sign_key(mock_get_llm, mock_update, client):
    user_id = "alice"
    old_profile = _profile(-0.8)
    new_profile = _profile(1.0)
    goal_id = _seed_goal_with_state(user_id, old_profile)
    mock_get_llm.return_value = MagicMock()
    mock_update.return_value = new_profile

    response = client.post(
        "/v1/update-learning-preferences",
        json={
            "learner_profile": str(old_profile),
            "learner_interactions": "{}",
            "learner_information": "",
            "user_id": user_id,
            "goal_id": goal_id,
        },
    )

    assert response.status_code == 200
    state = (store.get_goal(user_id, goal_id) or {}).get("adaptation_state", {})
    windows = state.get("evidence_windows", {})
    budget = state.get("daily_movement_budget", {})
    assert "fslsm_input:negative" not in windows
    assert "fslsm_input:positive" in windows
    assert "fslsm_perception:negative" in windows
    assert "fslsm_input" not in budget
    assert "fslsm_perception" in budget


@patch("main.update_learning_preferences_with_llm")
@patch("main.get_llm")
def test_submit_content_feedback_clears_only_old_sign_key(mock_get_llm, mock_update, client):
    user_id = "alice"
    old_profile = _profile(-0.8)
    new_profile = _profile(1.0)
    goal_id = _seed_goal_with_state(user_id, old_profile)
    mock_get_llm.return_value = MagicMock()
    mock_update.return_value = new_profile

    response = client.post(
        "/v1/submit-content-feedback",
        json={
            "user_id": user_id,
            "goal_id": goal_id,
            "feedback": {"note": "Prefer text-heavy explanations"},
        },
    )

    assert response.status_code == 200
    state = (store.get_goal(user_id, goal_id) or {}).get("adaptation_state", {})
    windows = state.get("evidence_windows", {})
    budget = state.get("daily_movement_budget", {})
    assert "fslsm_input:negative" not in windows
    assert "fslsm_input:positive" in windows
    assert "fslsm_perception:negative" in windows
    assert "fslsm_input" not in budget
    assert "fslsm_perception" in budget
