"""Endpoint and regression tests for the Ami tutor chat flow."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import auth_store, store  # noqa: E402
from modules.ai_chatbot_tutor.utils import safe_update_learning_preferences  # noqa: E402


@pytest.fixture()
def client():
    from main import app

    return TestClient(app)


@patch("main.chat_with_tutor_with_llm")
@patch("main.get_llm")
def test_chat_with_tutor_legacy_response_shape(mock_get_llm, mock_chat, client):
    mock_get_llm.return_value = MagicMock()
    mock_chat.return_value = "Hello from Ami"

    resp = client.post(
        "/v1/chat-with-tutor",
        json={
            "messages": "[{\"role\": \"user\", \"content\": \"Hello\"}]",
            "learner_profile": "{}",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"response": "Hello from Ami"}


@patch("main.chat_with_tutor_with_llm")
@patch("main.get_llm")
def test_chat_with_tutor_metadata_mode(mock_get_llm, mock_chat, client):
    mock_get_llm.return_value = MagicMock()
    mock_chat.return_value = {
        "response": "Here is an updated response.",
        "profile_updated": True,
        "updated_learner_profile": {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": -0.2}}},
        "retrieval_trace": {
            "contexts": [{"page_content": "Retrieved lecture content.", "source_type": "verified_content"}],
            "tool_calls": [{"tool_name": "retrieve_vector_context", "query": "Use more visuals"}],
        },
    }

    resp = client.post(
        "/v1/chat-with-tutor",
        json={
            "messages": "[{\"role\": \"user\", \"content\": \"Use more visuals\"}]",
            "learner_profile": "{}",
            "goal_context": {"course_code": "6.0001", "lecture_numbers": [1]},
            "return_metadata": True,
            "user_id": "alice",
            "goal_id": 0,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["response"]
    assert payload["profile_updated"] is True
    assert isinstance(payload.get("updated_learner_profile"), dict)
    assert payload["retrieval_trace"]["contexts"][0]["source_type"] == "verified_content"
    assert mock_chat.call_args.kwargs["goal_context"] == {"course_code": "6.0001", "lecture_numbers": [1]}


def test_chat_with_tutor_rejects_invalid_messages_format(client):
    resp = client.post(
        "/v1/chat-with-tutor",
        json={
            "messages": "hello",
            "learner_profile": "{}",
        },
    )
    assert resp.status_code == 400
    assert "messages must be a JSON array string" in resp.json().get("detail", "")


def test_safe_preference_update_uses_snapshot_and_sign_flip_reset():
    import main

    goal = store.create_goal(
        "alice",
        {
            "learning_goal": "Learn Python",
            "learning_path": [{"id": "Session 0"}],
            "adaptation_state": {},
        },
    )
    store.upsert_profile(
        "alice",
        goal["id"],
        {
            "learning_goal": "Learn Python",
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": 0.0,
                    "fslsm_perception": 0.0,
                    "fslsm_input": 0.2,
                    "fslsm_understanding": 0.0,
                }
            },
            "cognitive_status": {"mastered_skills": [], "in_progress_skills": []},
        },
    )

    updated_profile = {
        "learning_goal": "Learn Python",
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_input": -0.4,
                "fslsm_understanding": 0.0,
            }
        },
        "cognitive_status": {"mastered_skills": [], "in_progress_skills": []},
    }

    with patch("main.update_learning_preferences_with_llm", return_value=updated_profile), patch(
        "main._reset_adaptation_on_profile_sign_flip"
    ) as mock_reset:
        merged, profile_updated = safe_update_learning_preferences(
            llm=MagicMock(),
            learner_interactions={"additional_comments": "Please use more visual diagrams."},
            learner_information="",
            user_id="alice",
            goal_id=goal["id"],
            get_profile_fn=store.get_profile,
            save_snapshot_fn=store.save_profile_snapshot,
            record_snapshot_timestamp_fn=main._record_snapshot_timestamp,
            update_learning_preferences_fn=main.update_learning_preferences_with_llm,
            reset_adaptation_on_sign_flip_fn=main._reset_adaptation_on_profile_sign_flip,
            upsert_profile_fn=store.upsert_profile,
            refresh_goal_profile_fn=main._refresh_goal_profile,
        )

    assert profile_updated is True
    assert isinstance(merged, dict)
    assert store.get_profile_snapshot("alice", goal["id"]) is not None
    persisted = store.get_profile("alice", goal["id"])
    assert persisted["learning_preferences"]["fslsm_dimensions"]["fslsm_input"] == -0.4
    mock_reset.assert_called_once()


def test_safe_preference_update_caps_fslsm_delta_to_point_05():
    import main

    goal = store.create_goal(
        "alice",
        {
            "learning_goal": "Learn Python",
            "learning_path": [{"id": "Session 0"}],
            "adaptation_state": {},
        },
    )
    store.upsert_profile(
        "alice",
        goal["id"],
        {
            "learning_goal": "Learn Python",
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": 0.0,
                    "fslsm_perception": 0.0,
                    "fslsm_input": 0.2,
                    "fslsm_understanding": 0.0,
                }
            },
            "cognitive_status": {"mastered_skills": [], "in_progress_skills": []},
        },
    )

    # LLM proposes a large single-step jump; helper should cap to +/-0.05.
    updated_profile = {
        "learning_goal": "Learn Python",
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": -1.0,
                "fslsm_perception": 1.0,
                "fslsm_input": -0.8,
                "fslsm_understanding": 0.9,
            }
        },
        "cognitive_status": {"mastered_skills": [], "in_progress_skills": []},
    }

    with patch("main.update_learning_preferences_with_llm", return_value=updated_profile):
        merged, profile_updated = safe_update_learning_preferences(
            llm=MagicMock(),
            learner_interactions={"additional_comments": "I prefer visuals."},
            learner_information="",
            user_id="alice",
            goal_id=goal["id"],
            max_fslsm_delta=0.05,
            get_profile_fn=store.get_profile,
            save_snapshot_fn=store.save_profile_snapshot,
            record_snapshot_timestamp_fn=main._record_snapshot_timestamp,
            update_learning_preferences_fn=main.update_learning_preferences_with_llm,
            reset_adaptation_on_sign_flip_fn=main._reset_adaptation_on_profile_sign_flip,
            upsert_profile_fn=store.upsert_profile,
            refresh_goal_profile_fn=main._refresh_goal_profile,
        )

    assert profile_updated is True
    dims = merged["learning_preferences"]["fslsm_dimensions"]
    assert dims["fslsm_input"] == 0.15  # 0.2 -> capped downward by 0.05
    assert dims["fslsm_processing"] == -0.05
    assert dims["fslsm_perception"] == 0.05
    assert dims["fslsm_understanding"] == 0.05
