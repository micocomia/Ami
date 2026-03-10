"""Tests for mastery feedback persistence and reset endpoints."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import store


@pytest.fixture()
def client():
    from main import app

    return TestClient(app)


def _seed_goal_and_quiz(user_id: str = "alice"):
    goal = store.create_goal(
        user_id,
        {
            "learning_goal": "Mastery endpoint test",
            "learning_path": [
                {
                    "id": "S1",
                    "title": "Session 1",
                    "if_learned": False,
                    "navigation_mode": "linear",
                    "desired_outcome_when_completed": [{"name": "Skill A", "level": "intermediate"}],
                }
            ],
        },
    )
    goal_id = int(goal["id"])
    quiz_data = {
        "single_choice_questions": [
            {
                "question": "What is 2+2?",
                "options": ["3", "4", "5"],
                "correct_option": 1,
                "explanation": "2+2 equals 4.",
            }
        ],
        "multiple_choice_questions": [
            {
                "question": "Select primes",
                "options": ["2", "4", "5"],
                "correct_options": [0, 2],
                "explanation": "2 and 5 are prime.",
            }
        ],
        "true_false_questions": [
            {
                "question": "The sky is green.",
                "correct_answer": False,
                "explanation": "It is not green.",
            }
        ],
        "short_answer_questions": [],
        "open_ended_questions": [],
    }
    store.upsert_learning_content(
        user_id,
        goal_id,
        0,
        {
            "document": "Test document",
            "quizzes": quiz_data,
        },
    )
    return goal_id


@patch("main.get_llm")
def test_evaluate_mastery_persists_mastery_feedback(mock_get_llm, client):
    mock_get_llm.return_value = MagicMock()
    user_id = "alice"
    goal_id = _seed_goal_and_quiz(user_id)

    response = client.post(
        "/v1/evaluate-mastery",
        json={
            "user_id": user_id,
            "goal_id": goal_id,
            "session_index": 0,
            "quiz_answers": {
                "single_choice_questions": ["3"],
                "multiple_choice_questions": [["2", "4"]],
                "true_false_questions": ["False"],
                "short_answer_questions": [],
                "open_ended_questions": [],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "updated_session" in payload
    assert "quiz_feedback" in payload

    updated_session = payload["updated_session"]
    assert "mastery_feedback" in updated_session
    quiz_feedback = updated_session["mastery_feedback"]["quiz_feedback"]
    assert len(quiz_feedback["single_choice_questions"]) == 1
    assert quiz_feedback["single_choice_questions"][0]["is_correct"] is False
    assert quiz_feedback["multiple_choice_questions"][0]["is_correct"] is False
    assert quiz_feedback["true_false_questions"][0]["is_correct"] is True

    stored_goal = store.get_goal(user_id, goal_id)
    stored_session = stored_goal["learning_path"][0]
    assert "mastery_feedback" in stored_session
    assert stored_session["mastery_feedback"]["quiz_feedback"]["single_choice_questions"][0]["user_answer"] == "3"


@patch("main.get_llm")
def test_reset_mastery_attempt_clears_persisted_fields(mock_get_llm, client):
    mock_get_llm.return_value = MagicMock()
    user_id = "alice"
    goal_id = _seed_goal_and_quiz(user_id)

    submit_resp = client.post(
        "/v1/evaluate-mastery",
        json={
            "user_id": user_id,
            "goal_id": goal_id,
            "session_index": 0,
            "quiz_answers": {
                "single_choice_questions": ["4"],
                "multiple_choice_questions": [["2", "5"]],
                "true_false_questions": ["False"],
                "short_answer_questions": [],
                "open_ended_questions": [],
            },
        },
    )
    assert submit_resp.status_code == 200

    reset_resp = client.post(
        "/v1/reset-mastery-attempt",
        json={
            "user_id": user_id,
            "goal_id": goal_id,
            "session_index": 0,
        },
    )
    assert reset_resp.status_code == 200
    payload = reset_resp.json()
    assert payload.get("ok") is True
    updated_session = payload.get("updated_session", {})
    assert "mastery_score" not in updated_session
    assert "is_mastered" not in updated_session
    assert "mastery_threshold" not in updated_session
    assert "mastery_feedback" not in updated_session

    stored_goal = store.get_goal(user_id, goal_id)
    stored_session = stored_goal["learning_path"][0]
    assert "mastery_score" not in stored_session
    assert "is_mastered" not in stored_session
    assert "mastery_threshold" not in stored_session
    assert "mastery_feedback" not in stored_session
