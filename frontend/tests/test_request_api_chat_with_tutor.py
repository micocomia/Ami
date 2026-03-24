import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_chat_with_tutor_includes_goal_context(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", types.SimpleNamespace(session_state={}))
    from utils import request_api

    captured = {}

    def _fake_make_post_request(endpoint, data, mock_path=None):
        captured["endpoint"] = endpoint
        captured["data"] = data
        return {"response": "ok", "profile_updated": False}

    monkeypatch.setattr(request_api, "make_post_request", _fake_make_post_request)

    response = request_api.chat_with_tutor(
        [{"role": "user", "content": "Explain functions"}],
        {"learning_goal": "Learn 6.0001"},
        goal_context={"course_code": "6.0001", "lecture_numbers": [1]},
        learner_information="I want to learn about 6.0001",
        return_metadata=True,
    )

    assert response == {"response": "ok", "profile_updated": False}
    assert captured["endpoint"] == request_api.API_NAMES["chat_with_tutor"]
    assert captured["data"]["goal_context"] == {"course_code": "6.0001", "lecture_numbers": [1]}
