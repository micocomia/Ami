"""Unit-style tests for frontend state goal-id normalization and goal persistence."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


class _FakeSessionState(dict):
    """dict with attribute-style access to mimic Streamlit SessionStateProxy."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture()
def state_module(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    frontend_dir = repo_root / "frontend"
    if str(frontend_dir) not in sys.path:
        sys.path.insert(0, str(frontend_dir))

    fake_streamlit = types.ModuleType("streamlit")
    fake_streamlit.session_state = _FakeSessionState()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    state_path = frontend_dir / "utils" / "state.py"
    spec = importlib.util.spec_from_file_location("frontend_state_under_test", state_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "save_persistent_state", lambda: True)
    return module


def test_add_new_goal_preserves_goal_context_and_returns_goal_id(state_module):
    state_module.st.session_state.goals = []
    state_module.st.session_state["to_add_goal"] = {}

    goal_id = state_module.add_new_goal(
        learning_goal="Learn Python",
        skill_gaps=[],
        goal_assessment=None,
        learner_profile={},
        learning_path=[],
        goal_context={"course_code": "DTI5902", "lecture_numbers": [1, 2]},
        retrieved_sources=[{"source_type": "verified_content"}],
    )

    assert goal_id == 0
    saved_goal = state_module.st.session_state.goals[0]
    assert saved_goal["id"] == 0
    assert saved_goal["goal_context"] == {"course_code": "DTI5902", "lecture_numbers": [1, 2]}
    assert saved_goal["retrieved_sources"] == [{"source_type": "verified_content"}]


def test_normalize_selected_goal_id_converts_index_to_goal_id(state_module):
    state_module.st.session_state["goals"] = [
        {"id": 10, "is_deleted": False},
        {"id": 42, "is_deleted": False},
    ]
    state_module.st.session_state["selected_goal_id"] = 1

    changed = state_module.normalize_selected_goal_id()

    assert changed is True
    assert state_module.st.session_state["selected_goal_id"] == 42


def test_normalize_selected_goal_id_keeps_existing_goal_id(state_module):
    state_module.st.session_state["goals"] = [
        {"id": 10, "is_deleted": False},
        {"id": 42, "is_deleted": False},
    ]
    state_module.st.session_state["selected_goal_id"] = 10

    changed = state_module.normalize_selected_goal_id()

    assert changed is False
    assert state_module.st.session_state["selected_goal_id"] == 10
