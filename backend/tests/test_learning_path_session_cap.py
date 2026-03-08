"""Tests for learning path session cap handling and overflow metadata."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learning_plan_generator.agents.learning_path_scheduler import LearningPathScheduler
from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import (
    schedule_learning_path_agentic,
)
from modules.learning_plan_generator.prompts.learning_path_scheduling import (
    learning_path_scheduler_system_prompt,
    learning_path_scheduler_task_prompt_session,
)
from modules.learning_plan_generator.schemas import (
    LearningPath,
    MAX_LEARNING_PATH_SESSIONS,
    MIN_LEARNING_PATH_SESSIONS,
)


def _session(session_index: int) -> dict:
    return {
        "id": f"Session {session_index}",
        "title": f"Topic {session_index}",
        "abstract": f"Session {session_index} overview",
        "if_learned": False,
        "associated_skills": ["Skill A"],
        "desired_outcome_when_completed": [{"name": "Skill A", "level": "beginner"}],
    }


@pytest.mark.parametrize("count", [MIN_LEARNING_PATH_SESSIONS, MAX_LEARNING_PATH_SESSIONS])
def test_learning_path_schema_accepts_session_count_bounds(count: int):
    validated = LearningPath.model_validate({"learning_path": [_session(i + 1) for i in range(count)]})
    assert len(validated.learning_path) == count


@pytest.mark.parametrize("count", [MIN_LEARNING_PATH_SESSIONS - 1, MAX_LEARNING_PATH_SESSIONS + 1])
def test_learning_path_schema_rejects_out_of_bounds_count(count: int):
    with pytest.raises(ValidationError, match="between 1 and 20 sessions"):
        LearningPath.model_validate({"learning_path": [_session(i + 1) for i in range(count)]})


def test_scheduler_trims_over_limit_output_and_records_observations(monkeypatch):
    over_limit_count = MAX_LEARNING_PATH_SESSIONS + 5

    def fake_invoke(self, input_dict, task_prompt=None, **kwargs):
        return {"learning_path": [_session(i + 1) for i in range(over_limit_count)]}

    monkeypatch.setattr(LearningPathScheduler, "invoke", fake_invoke)

    scheduler = LearningPathScheduler(MagicMock())
    result = scheduler.schedule_session({"learner_profile": {}, "session_count": 0})

    assert len(result["learning_path"]) == MAX_LEARNING_PATH_SESSIONS
    assert [s["id"] for s in result["learning_path"]] == [
        f"Session {i}" for i in range(1, MAX_LEARNING_PATH_SESSIONS + 1)
    ]
    assert scheduler.last_generation_observations == {
        "raw_session_count": over_limit_count,
        "effective_session_count": MAX_LEARNING_PATH_SESSIONS,
        "was_trimmed": True,
        "max_allowed_sessions": MAX_LEARNING_PATH_SESSIONS,
    }


def test_agentic_pipeline_forwards_generation_observations_and_surfaces_metadata():
    class FakeScheduler:
        def __init__(self, llm):
            self.last_generation_observations = {}

        def schedule_session(self, _payload):
            self.last_generation_observations = {
                "raw_session_count": MAX_LEARNING_PATH_SESSIONS + 3,
                "effective_session_count": MAX_LEARNING_PATH_SESSIONS,
                "was_trimmed": True,
                "max_allowed_sessions": MAX_LEARNING_PATH_SESSIONS,
            }
            return {"learning_path": [_session(i + 1) for i in range(MAX_LEARNING_PATH_SESSIONS)]}

        def reflexion(self, _payload):
            raise AssertionError("reflexion should not be called when first evaluation passes")

    mock_simulator_instance = MagicMock()
    mock_simulator_instance.feedback_path.return_value = {
        "feedback": {"progression": "Good", "engagement": "Good", "personalization": "Good"},
        "suggestions": {"progression": "", "engagement": "", "personalization": ""},
        "is_acceptable": True,
        "issues": [],
        "improvement_directives": "",
    }

    with patch(
        "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler",
        FakeScheduler,
    ), patch(
        "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPlanFeedbackSimulator",
        return_value=mock_simulator_instance,
    ), patch(
        "modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LLMFactory.create",
        return_value=MagicMock(),
    ):
        _, metadata = schedule_learning_path_agentic(
            llm=MagicMock(),
            learner_profile={"learning_goal": "Learn Python"},
            max_refinements=0,
        )

    feedback_payload = mock_simulator_instance.feedback_path.call_args.args[0]
    assert feedback_payload["generation_observations"]["was_trimmed"] is True
    assert metadata["final_generation_observations"]["was_trimmed"] is True
    assert metadata["generation_observations_history"][0]["raw_session_count"] == MAX_LEARNING_PATH_SESSIONS + 3


def test_learning_path_prompt_contract_updated_to_1_to_20():
    assert "between 1 and 20" in learning_path_scheduler_system_prompt
    assert "within [1, 20]" in learning_path_scheduler_task_prompt_session
    assert "1 and 10" not in learning_path_scheduler_system_prompt
    assert "[1, 10]" not in learning_path_scheduler_task_prompt_session
