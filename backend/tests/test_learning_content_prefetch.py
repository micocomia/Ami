"""Tests for backend-owned prefetch and single-flight content generation."""

import json
import logging
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import store


def _session(session_id: str, *, learned: bool = False, title: str = ""):
    return {
        "id": session_id,
        "title": title or session_id,
        "abstract": "Session abstract",
        "if_learned": learned,
        "associated_skills": ["Skill A"],
        "desired_outcome_when_completed": [{"name": "Skill A", "level": "beginner"}],
    }


def _fake_learning_content(*_args, **_kwargs):
    return {
        "document": "## Prefetched Content\n\nBody",
        "quizzes": {"single_choice_questions": []},
        "sources_used": [],
        "content_format": "standard",
    }


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if predicate():
            return True
        time.sleep(0.02)
    return False


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
def _reset_prefetch_state():
    import main

    main.PREFETCH_SERVICE.reset_for_test()
    yield


@pytest.fixture()
def client():
    from main import app

    return TestClient(app)


def _seed_goal(user_id: str = "alice", *, learning_path=None) -> int:
    goal = store.create_goal(
        user_id,
        {
            "learning_goal": "Learn Python",
            "skill_gaps": [],
            "learning_path": learning_path or [],
            "goal_context": {"topic": "python"},
        },
    )
    store.upsert_profile(user_id, goal["id"], {"learning_preferences": {"fslsm_dimensions": {}}})
    return goal["id"]


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_patch_goal_with_changed_learning_path_enqueues_prefetch(mock_generate, _mock_llm, client):
    goal_id = _seed_goal(learning_path=[])
    updated_path = [_session("Session 1")]

    resp = client.patch(f"/goals/alice/{goal_id}", json={"learning_path": updated_path})
    assert resp.status_code == 200

    assert _wait_until(lambda: store.get_learning_content("alice", goal_id, 0) is not None)
    assert mock_generate.call_count == 1


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_patch_goal_without_learning_path_change_does_not_prefetch(mock_generate, _mock_llm, client):
    goal_id = _seed_goal(learning_path=[_session("Session 1")])

    resp = client.patch(f"/goals/alice/{goal_id}", json={"learning_goal": "Learn Python Deeply"})
    assert resp.status_code == 200
    time.sleep(0.15)
    assert mock_generate.call_count == 0


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_session_start_prefetches_next_session_only(mock_generate, _mock_llm, client):
    goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2"), _session("Session 3")])

    resp = client.post(
        "/session-activity",
        json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
    )
    assert resp.status_code == 200

    assert _wait_until(lambda: store.get_learning_content("alice", goal_id, 1) is not None)
    assert store.get_learning_content("alice", goal_id, 0) is None
    assert mock_generate.call_count == 1


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_prefetch_skips_when_cache_exists(mock_generate, _mock_llm, client):
    goal_id = _seed_goal(learning_path=[_session("Session 1")])
    store.upsert_learning_content(
        "alice",
        goal_id,
        0,
        {"document": "Cached", "quizzes": {}, "sources_used": [], "content_format": "standard"},
    )

    resp = client.patch(f"/goals/alice/{goal_id}", json={"learning_path": [_session("Session 1", title="Updated")]})
    assert resp.status_code == 200
    time.sleep(0.15)
    assert mock_generate.call_count == 0


@patch("main.get_llm", return_value=MagicMock())
def test_duplicate_trigger_while_inflight_does_not_duplicate_generation(_mock_llm, client, monkeypatch):
    import main

    monkeypatch.setitem(main.APP_CONFIG, "prefetch_cooldown_secs", 0)

    call_count = {"value": 0}

    def _slow_generate(*_args, **_kwargs):
        call_count["value"] += 1
        time.sleep(0.3)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1")])
        r1 = client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        r2 = client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert _wait_until(lambda: store.get_learning_content("alice", goal_id, 0) is not None, timeout=4)
        assert call_count["value"] == 1


@patch("main.get_llm", return_value=MagicMock())
def test_get_learning_content_waits_for_inflight_prefetch(_mock_llm, client):
    def _slow_generate(*_args, **_kwargs):
        time.sleep(0.2)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        resp = client.get(f"/learning-content/alice/{goal_id}/0")
        assert resp.status_code == 200
        assert "document" in resp.json()


@patch("main.get_llm", return_value=MagicMock())
def test_generate_learning_content_joins_inflight_without_duplicate_generation(_mock_llm, client):
    call_count = {"value": 0}

    def _slow_generate(*_args, **_kwargs):
        call_count["value"] += 1
        time.sleep(0.2)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        payload = {
            "learner_profile": json.dumps({}),
            "learning_path": json.dumps([_session("Session 1")]),
            "learning_session": json.dumps(_session("Session 1")),
            "use_search": True,
            "allow_parallel": True,
            "with_quiz": True,
            "method_name": "ami",
            "user_id": "alice",
            "goal_id": goal_id,
            "session_index": 0,
        }
        resp = client.post("/generate-learning-content", json=payload)
        assert resp.status_code == 200
        assert call_count["value"] == 1


@patch("main.get_llm", return_value=MagicMock())
def test_target_session_change_discards_prefetch_write(_mock_llm, client):
    import main

    def _slow_generate(*_args, **_kwargs):
        time.sleep(0.2)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1", title="Old")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        store.patch_goal("alice", goal_id, {"learning_path": [_session("Session 1", title="New")]})
        cache_key = f"alice:{goal_id}:0"
        assert _wait_until(
            lambda: main.PREFETCH_SERVICE.singleflight_status(cache_key) != "running",
            timeout=2.5,
        )
        assert store.get_learning_content("alice", goal_id, 0) is None


@patch("main.get_llm", return_value=MagicMock())
def test_unrelated_session_runtime_change_does_not_discard_prefetch_write(_mock_llm, client):
    import main

    def _slow_generate(*_args, **_kwargs):
        time.sleep(0.25)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
        )
        time.sleep(0.05)
        goal = store.get_goal("alice", goal_id) or {}
        learning_path = goal.get("learning_path", [])
        learning_path[0]["mastery_score"] = 90.0
        learning_path[0]["is_mastered"] = True
        learning_path[0]["mastery_threshold"] = 70.0
        store.patch_goal("alice", goal_id, {"learning_path": learning_path})
        cache_key = f"alice:{goal_id}:1"
        assert _wait_until(
            lambda: main.PREFETCH_SERVICE.singleflight_status(cache_key) != "running",
            timeout=3.0,
        )
        assert store.get_learning_content("alice", goal_id, 1) is not None


@patch("main.get_llm", return_value=MagicMock())
def test_target_session_learned_discards_prefetch_write(_mock_llm, client):
    import main

    def _slow_generate(*_args, **_kwargs):
        time.sleep(0.25)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
        )
        time.sleep(0.05)
        goal = store.get_goal("alice", goal_id) or {}
        learning_path = goal.get("learning_path", [])
        learning_path[1]["if_learned"] = True
        store.patch_goal("alice", goal_id, {"learning_path": learning_path})
        cache_key = f"alice:{goal_id}:1"
        assert _wait_until(
            lambda: main.PREFETCH_SERVICE.singleflight_status(cache_key) != "running",
            timeout=3.0,
        )
        assert store.get_learning_content("alice", goal_id, 1) is None


@patch("main.get_llm", return_value=MagicMock())
def test_on_demand_owner_unrelated_session_change_still_saves(_mock_llm, client):
    call_count = {"value": 0}

    def _slow_generate(*_args, **_kwargs):
        call_count["value"] += 1
        goal = store.get_goal("alice", goal_id) or {}
        learning_path = goal.get("learning_path", [])
        learning_path[0]["mastery_score"] = 85.0
        learning_path[0]["is_mastered"] = True
        learning_path[0]["mastery_threshold"] = 70.0
        store.patch_goal("alice", goal_id, {"learning_path": learning_path})
        time.sleep(0.2)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2")])
        payload = {
            "learner_profile": json.dumps({}),
            "learning_path": json.dumps([_session("Session 1"), _session("Session 2")]),
            "learning_session": json.dumps(_session("Session 2")),
            "use_search": True,
            "allow_parallel": True,
            "with_quiz": True,
            "method_name": "ami",
            "user_id": "alice",
            "goal_id": goal_id,
            "session_index": 1,
        }
        resp = client.post("/generate-learning-content", json=payload)
        assert resp.status_code == 200
        assert call_count["value"] == 1
        assert store.get_learning_content("alice", goal_id, 1) is not None


@patch("main.get_llm", return_value=MagicMock())
@patch("main.create_simulate_feedback_tool")
@patch("main.reschedule_learning_path_with_llm")
@patch("modules.tools.plan_regeneration_tool.decide_regeneration")
def test_adapt_applied_invalidates_only_changed_future_sessions(
    mock_decide,
    mock_reschedule,
    mock_sim_tool,
    _mock_llm,
    client,
    monkeypatch,
):
    import main
    from modules.tools.plan_regeneration_tool import RegenerationDecision

    monkeypatch.setitem(main.APP_CONFIG, "prefetch_enabled", False)

    path_before = [
        _session("Session 1", learned=True, title="Done"),
        _session("Session 2", learned=False, title="Old Future"),
        _session("Session 3", learned=False, title="Keep Future"),
    ]
    goal_id = _seed_goal(learning_path=path_before)
    store.upsert_learning_content("alice", goal_id, 1, _fake_learning_content())
    store.upsert_learning_content("alice", goal_id, 2, _fake_learning_content())

    mock_decide.return_value = RegenerationDecision(
        action="adjust_future",
        reason="Adjust future sessions",
        affected_sessions=[1, 2],
    )
    mock_reschedule.return_value = {
        "learning_path": [
            _session("Session 1", learned=True, title="Done"),
            _session("Session 2", learned=False, title="Changed Future"),
            _session("Session 3", learned=False, title="Keep Future"),
        ]
    }
    sim_tool = MagicMock()
    sim_tool.invoke.return_value = {"is_acceptable": True, "issues": [], "feedback": {}}
    mock_sim_tool.return_value = sim_tool

    resp = client.post(
        "/adapt-learning-path",
        json={"user_id": "alice", "goal_id": goal_id, "force": True},
    )
    assert resp.status_code == 200
    assert store.get_learning_content("alice", goal_id, 1) is None
    assert store.get_learning_content("alice", goal_id, 2) is not None


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_session_start_cooldown_blocks_rapid_repeat_prefetch(mock_generate, _mock_llm, client, monkeypatch):
    import main

    monkeypatch.setitem(main.APP_CONFIG, "prefetch_cooldown_secs", 30)
    goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2")])

    first = client.post(
        "/session-activity",
        json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
    )
    assert first.status_code == 200
    assert _wait_until(lambda: store.get_learning_content("alice", goal_id, 1) is not None)
    store.delete_learning_content("alice", goal_id, 1)

    second = client.post(
        "/session-activity",
        json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
    )
    assert second.status_code == 200
    time.sleep(0.2)
    assert mock_generate.call_count == 1


@patch("main.get_llm", return_value=MagicMock())
def test_generate_content_join_does_not_return_504_even_with_tiny_timeout(_mock_llm, client, monkeypatch):
    import main

    monkeypatch.setitem(main.APP_CONFIG, "prefetch_wait_long_secs", 0)

    call_count = {"value": 0}

    def _slow_generate(*_args, **_kwargs):
        call_count["value"] += 1
        time.sleep(0.35)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        payload = {
            "learner_profile": json.dumps({}),
            "learning_path": json.dumps([_session("Session 1")]),
            "learning_session": json.dumps(_session("Session 1")),
            "use_search": True,
            "allow_parallel": True,
            "with_quiz": True,
            "method_name": "ami",
            "user_id": "alice",
            "goal_id": goal_id,
            "session_index": 0,
        }
        resp = client.post("/generate-learning-content", json=payload)
        assert resp.status_code == 200
        assert "document" in resp.json()
        assert call_count["value"] == 1


@patch("main.get_llm", return_value=MagicMock())
@patch("main.generate_learning_content_with_llm", side_effect=_fake_learning_content)
def test_logging_contains_session_and_trigger_trace(_mock_generate, _mock_llm, client, caplog):
    caplog.set_level(logging.INFO)
    goal_id = _seed_goal(learning_path=[_session("Session 1"), _session("Session 2")])

    client.patch(f"/goals/alice/{goal_id}", json={"learning_path": [_session("Session 1"), _session("Session 2")]})
    client.post(
        "/session-activity",
        json={"user_id": "alice", "goal_id": goal_id, "session_index": 0, "event_type": "start"},
    )
    client.get(f"/learning-content/alice/{goal_id}/0")
    client.post(
        "/generate-learning-content",
        json={
            "learner_profile": json.dumps({}),
            "learning_path": json.dumps([_session("Session 1"), _session("Session 2")]),
            "learning_session": json.dumps(_session("Session 1")),
            "method_name": "ami",
            "user_id": "alice",
            "goal_id": goal_id,
            "session_index": 0,
        },
    )

    text = "\n".join(rec.getMessage() for rec in caplog.records if "content-trace" in rec.getMessage())
    assert '"user_id": "alice"' in text
    assert f'"goal_id": {goal_id}' in text
    assert '"session_index": 0' in text
    assert '"status":' in text
    assert '"path_hash":' in text
    assert '"duration_ms":' in text
    assert '"trigger_source": "session_start"' in text or '"trigger_source": "on_demand"' in text


@patch("main.get_llm", return_value=MagicMock())
def test_worker_discard_logs_stale_reason(_mock_llm, client, caplog):
    import main

    caplog.set_level(logging.INFO)

    def _slow_generate(*_args, **_kwargs):
        time.sleep(0.2)
        return _fake_learning_content()

    with patch("main.generate_learning_content_with_llm", side_effect=_slow_generate):
        goal_id = _seed_goal(learning_path=[_session("Session 1", title="Old")])
        client.post(
            "/session-activity",
            json={"user_id": "alice", "goal_id": goal_id, "session_index": -1, "event_type": "start"},
        )
        store.patch_goal("alice", goal_id, {"learning_path": [_session("Session 1", title="New")]})
        cache_key = f"alice:{goal_id}:0"
        assert _wait_until(
            lambda: main.PREFETCH_SERVICE.singleflight_status(cache_key) != "running",
            timeout=2.5,
        )
    text = "\n".join(rec.getMessage() for rec in caplog.records if "content-trace" in rec.getMessage())
    assert '"stale_reason": "session_changed"' in text


def test_prefetch_service_utility_methods():
    import main

    service = main.PREFETCH_SERVICE
    assert service.content_cache_key("alice", 1, 2) == "alice:1:2"

    learning_path = [
        _session("Session 1", learned=True),
        _session("Session 2", learned=False),
    ]
    assert service.first_unlearned_session_index(learning_path) == 1
    assert service.first_unlearned_session_index(learning_path, start_after=1) is None

    before = [_session("Session 1", learned=True), _session("Session 2", title="A"), _session("Session 3", title="B")]
    after = [_session("Session 1", learned=True), _session("Session 2", title="A2"), _session("Session 3", title="B")]
    assert service.changed_unlearned_indices(before, after) == [1]
