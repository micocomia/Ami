"""Tests for Ami tutor tools."""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.ai_chatbot_tutor.tools import (  # noqa: E402
    create_retrieve_session_learning_content_tool,
    create_retrieve_vector_context_tool,
    create_search_media_resources_tool,
    create_search_web_context_ephemeral_tool,
    create_update_learning_preferences_from_signal_tool,
)
from modules.ai_chatbot_tutor.tools import update_learning_preferences_from_signal_tool as pref_signal_tool_mod  # noqa: E402
from utils import store  # noqa: E402


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


def _seed_goal_with_content():
    goal = store.create_goal(
        "alice",
        {
            "learning_goal": "Learn recursion",
            "learning_path": [
                {"id": "Session 0", "title": "Intro"},
                {"id": "Session 1", "title": "Recursion"},
                {"id": "Session 2", "title": "Trees"},
            ],
        },
    )
    store.upsert_learning_content(
        "alice",
        goal["id"],
        0,
        {"document": "## Basics\nLoops and variables.", "quizzes": {}},
    )
    store.upsert_learning_content(
        "alice",
        goal["id"],
        1,
        {"document": "## Recursion\nRecursion uses base case and recursive step.", "quizzes": {}},
    )
    store.upsert_learning_content(
        "alice",
        goal["id"],
        2,
        {"document": "## Trees\nTree traversal can use recursion.", "quizzes": {}},
    )
    return goal["id"]


def test_retrieve_session_learning_content_prefers_current_then_fallback():
    goal_id = _seed_goal_with_content()
    tool = create_retrieve_session_learning_content_tool()

    output = tool.invoke({
        "query": "recursion base case",
        "user_id": "alice",
        "goal_id": goal_id,
        "session_index": 0,
        "top_k": 2,
    })
    src0 = f"learning_content:alice:{goal_id}:0"
    src1 = f"learning_content:alice:{goal_id}:1"
    assert src0 in output
    assert src1 in output
    assert output.find(src0) < output.find(src1)


def test_retrieve_session_learning_content_fallback_when_session_invalid():
    goal_id = _seed_goal_with_content()
    tool = create_retrieve_session_learning_content_tool()

    output = tool.invoke({
        "query": "recursive step",
        "user_id": "alice",
        "goal_id": goal_id,
        "session_index": 99,
        "top_k": 2,
    })
    assert f"learning_content:alice:{goal_id}:1" in output


def test_vector_tool_uses_vector_retrieval_only():
    manager = SimpleNamespace(
        retrieve=MagicMock(return_value=[Document(page_content="Vector fact", metadata={"source": "vs"})]),
        invoke=MagicMock(side_effect=AssertionError("invoke() must not be used")),
    )
    tool = create_retrieve_vector_context_tool(manager)

    output = tool.invoke({"query": "fact", "top_k": 1})
    assert "Vector fact" in output
    manager.retrieve.assert_called_once()
    manager.invoke.assert_not_called()


def test_web_tool_is_ephemeral_and_non_persistent():
    mock_runner = SimpleNamespace(
        invoke=MagicMock(return_value=[
            SimpleNamespace(
                title="Recursion article",
                link="https://example.com/recursion",
                snippet="A quick recursion explainer",
                content="Recursion repeats the same function until a base case.",
            )
        ])
    )
    manager = SimpleNamespace(search_runner=mock_runner, invoke=MagicMock())
    tool = create_search_web_context_ephemeral_tool(manager)

    output = tool.invoke({"query": "recursion", "top_k": 1})
    assert "https://example.com/recursion" in output
    manager.invoke.assert_not_called()
    mock_runner.invoke.assert_called_once()


def test_media_tool_normalizes_output(monkeypatch):
    from modules.ai_chatbot_tutor.tools import search_media_resources_tool as tutor_tools_mod

    monkeypatch.setattr(
        tutor_tools_mod,
        "find_media_resources",
        lambda *_args, **_kwargs: [
            {
                "type": "video",
                "title": "Recursion Visual Tutorial",
                "url": "https://youtube.com/watch?v=abc123xyz00",
                "snippet": "A visual walk-through",
                "source": "youtube",
            }
        ],
    )
    monkeypatch.setattr(
        tutor_tools_mod,
        "filter_media_resources_with_llm",
        lambda _llm, resources, **_kwargs: resources,
    )

    manager = SimpleNamespace(search_runner=SimpleNamespace())
    tool = create_search_media_resources_tool(
        search_rag_manager=manager,
        llm=object(),
        enable_llm_filter=False,
    )
    output = tool.invoke({"query": "recursion"})
    payload = json.loads(output)
    assert "media_resources" in payload
    assert payload["media_resources"][0]["type"] == "video"
    assert payload["media_resources"][0]["url"]


def test_preference_update_signal_gate_and_sink(monkeypatch):
    sink = {}
    calls = {"count": 0}

    def _safe_update(**_kwargs):
        calls["count"] += 1
        return {
            "profile_updated": True,
            "updated_learner_profile": {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": -0.3}}},
            "reason": "Updated.",
        }

    def _mock_classify(message, _llm, *, confidence_threshold):
        if "thanks" in message:
            return {}
        assert confidence_threshold == pytest.approx(0.6)
        return {
            "fslsm_input:negative": ["more visual diagrams"],
            "fslsm_understanding:negative": ["step by step examples"],
        }

    monkeypatch.setattr(pref_signal_tool_mod, "_classify_preference_signals_with_llm", _mock_classify)
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink=sink,
        signal_classifier_llm=object(),
    )

    no_update = json.loads(tool.invoke({
        "latest_user_message": "thanks that helps",
        "user_id": "alice",
        "goal_id": 0,
    }))
    assert no_update["profile_updated"] is False
    assert calls["count"] == 0

    yes_update = json.loads(tool.invoke({
        "latest_user_message": "Please use more visual diagrams and step by step examples",
        "user_id": "alice",
        "goal_id": 0,
    }))
    assert yes_update["profile_updated"] is True
    assert calls["count"] == 1
    assert "fslsm_input:negative" in yes_update["signals"]
    assert "fslsm_understanding:negative" in yes_update["signals"]
    assert sink.get("profile_updated") is True
    assert isinstance(sink.get("updated_learner_profile"), dict)


def test_preference_update_detects_verbal_over_visual_signal(monkeypatch):
    captured = {}

    def _safe_update(**kwargs):
        captured.update(kwargs)
        return {
            "profile_updated": True,
            "updated_learner_profile": {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": 0.2}}},
            "reason": "Updated.",
        }

    monkeypatch.setattr(
        pref_signal_tool_mod,
        "_classify_preference_signals_with_llm",
        lambda _message, _llm, *, confidence_threshold: {
            "fslsm_input:positive": ["more verbal instructions"],
        },
    )
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
        signal_classifier_llm=object(),
    )
    payload = json.loads(tool.invoke({
        "latest_user_message": "Could you give me more verbal instructions as opposed to visual diagrams?",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is True
    assert isinstance(captured.get("signals"), dict)
    assert "fslsm_input:positive" in captured["signals"]


def test_preference_update_detects_processing_and_perception_signals(monkeypatch):
    captured = {}

    def _safe_update(**kwargs):
        captured.update(kwargs)
        return {
            "profile_updated": True,
            "updated_learner_profile": {"learning_preferences": {"fslsm_dimensions": {"fslsm_processing": -0.2}}},
            "reason": "Updated.",
        }

    monkeypatch.setattr(
        pref_signal_tool_mod,
        "_classify_preference_signals_with_llm",
        lambda _message, _llm, *, confidence_threshold: {
            "fslsm_processing:negative": ["hands-on exercises"],
            "fslsm_perception:positive": ["conceptual framework first"],
        },
    )
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
        signal_classifier_llm=object(),
    )

    payload = json.loads(tool.invoke({
        "latest_user_message": "I learn best with hands-on work, but please start with the theory.",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is True
    assert "fslsm_processing:negative" in captured["signals"]
    assert "fslsm_perception:positive" in captured["signals"]


def test_preference_update_low_confidence_results_in_no_update(monkeypatch):
    calls = {"count": 0}

    def _safe_update(**_kwargs):
        calls["count"] += 1
        return {"profile_updated": True}

    monkeypatch.setattr(
        pref_signal_tool_mod,
        "_classify_preference_signals_with_llm",
        lambda _message, _llm, *, confidence_threshold: {},
    )
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
        signal_classifier_llm=object(),
        signal_confidence_threshold=0.7,
    )

    payload = json.loads(tool.invoke({
        "latest_user_message": "Maybe visuals could help, not sure.",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is False
    assert "confidence >= 0.70" in payload["reason"]
    assert calls["count"] == 0


def test_preference_update_classifier_failure_is_safe(monkeypatch):
    calls = {"count": 0}

    def _safe_update(**_kwargs):
        calls["count"] += 1
        return {"profile_updated": True}

    def _raise_invalid_json(*_args, **_kwargs):
        raise ValueError("invalid JSON")

    monkeypatch.setattr(pref_signal_tool_mod, "_classify_preference_signals_with_llm", _raise_invalid_json)
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
        signal_classifier_llm=object(),
    )

    payload = json.loads(tool.invoke({
        "latest_user_message": "Please adapt to my style.",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is False
    assert payload["signals"] == {}
    assert "Preference signal classification failed" in payload["reason"]
    assert calls["count"] == 0


def test_preference_update_handles_classifier_initialization_failure(monkeypatch):
    calls = {"count": 0}

    def _safe_update(**_kwargs):
        calls["count"] += 1
        return {"profile_updated": True}

    def _raise_init_failure(**_kwargs):
        raise RuntimeError("model bootstrap failed")

    monkeypatch.setattr(pref_signal_tool_mod.LLMFactory, "create", _raise_init_failure)
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
    )

    payload = json.loads(tool.invoke({
        "latest_user_message": "Please use visuals and step by step flow.",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is False
    assert payload["signals"] == {}
    assert "classifier is unavailable" in payload["reason"]
    assert calls["count"] == 0


def test_preference_update_explicit_input_vector_correction(monkeypatch):
    captured = {}

    def _safe_update(**kwargs):
        captured.update(kwargs)
        return {
            "profile_updated": True,
            "updated_learner_profile": {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": 0.3}}},
            "reason": "Updated.",
        }

    monkeypatch.setattr(
        pref_signal_tool_mod,
        "_classify_preference_signals_with_llm",
        lambda message, _llm, *, confidence_threshold: {
            "fslsm_input:positive": ["I should be a verbal learner"],
        } if "input vector is wrong" in message else {},
    )
    tool = create_update_learning_preferences_from_signal_tool(
        safe_update_fn=_safe_update,
        sink={},
        signal_classifier_llm=object(),
    )

    payload = json.loads(tool.invoke({
        "latest_user_message": "I think my input vector is wrong, I should be a verbal learner",
        "user_id": "alice",
        "goal_id": 0,
    }))

    assert payload["profile_updated"] is True
    assert "fslsm_input:positive" in captured["signals"]
