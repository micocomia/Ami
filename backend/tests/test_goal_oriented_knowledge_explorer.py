import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.GoalOrientedKnowledgeExplorer.invoke")
def test_explorer_retries_once_and_returns_strict_schema(mock_invoke):
    from modules.content_generator.agents.goal_oriented_knowledge_explorer import (
        GoalOrientedKnowledgeExplorer,
    )

    mock_invoke.side_effect = [
        {
            "knowledge_points": [
                {"name": "Basic French Sentence Structure", "role": "foundation", "solo_level": "beginner"},
            ]
        },
        {
            "knowledge_points": [
                {"name": "Basic French Sentence Structure", "role": "foundational", "solo_level": "beginner"},
                {"name": "Common French Phrases", "role": "practical", "solo_level": "intermediate"},
                {"name": "Conversation Strategy", "role": "strategic", "solo_level": "advanced"},
            ]
        },
    ]

    explorer = GoalOrientedKnowledgeExplorer(MagicMock())
    output = explorer.explore(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Intro to French"},
            "session_adaptation_contract": "{}",
        }
    )

    assert mock_invoke.call_count == 2
    assert output["knowledge_points"][0]["role"] == "foundational"
    assert output["knowledge_points"][1]["role"] == "practical"
    assert output["knowledge_points"][2]["role"] == "strategic"
    assert output["knowledge_points"][0]["solo_level"] == "beginner"
    assert output["knowledge_points"][1]["solo_level"] == "intermediate"
    assert output["knowledge_points"][2]["solo_level"] == "advanced"


@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.GoalOrientedKnowledgeExplorer.invoke")
def test_explorer_raises_after_failed_repair_retry(mock_invoke):
    from modules.content_generator.agents.goal_oriented_knowledge_explorer import (
        GoalOrientedKnowledgeExplorer,
    )

    mock_invoke.side_effect = [
        {"knowledge_points": [{"name": "A", "role": "example", "solo_level": "beginner"}]},
        {"knowledge_points": [{"name": "A", "role": "example", "solo_level": "beginner"}]},
    ]

    explorer = GoalOrientedKnowledgeExplorer(MagicMock())
    with pytest.raises(ValidationError):
        explorer.explore(
            {
                "learner_profile": {},
                "learning_path": {},
                "learning_session": {"title": "Intro to French"},
                "session_adaptation_contract": "{}",
            }
        )


@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.GoalOrientedKnowledgeExplorer.invoke")
def test_explorer_filters_generic_points_and_deduplicates(mock_invoke):
    from modules.content_generator.agents.goal_oriented_knowledge_explorer import (
        GoalOrientedKnowledgeExplorer,
    )

    mock_invoke.return_value = {
        "knowledge_points": [
            {"name": "Introduction", "role": "foundational", "solo_level": "beginner"},
            {"name": "String Slicing", "role": "foundational", "solo_level": "beginner"},
            {"name": " string   slicing ", "role": "foundational", "solo_level": "beginner"},
            {"name": "Summary", "role": "practical", "solo_level": "intermediate"},
        ]
    }

    explorer = GoalOrientedKnowledgeExplorer(MagicMock())
    output = explorer.explore(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Python Strings"},
            "session_adaptation_contract": "{}",
        }
    )
    names = [item["name"] for item in output["knowledge_points"]]
    assert names == ["String Slicing"]


@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.GoalOrientedKnowledgeExplorer.invoke")
def test_explorer_applies_application_first_tie_break_order(mock_invoke):
    from modules.content_generator.agents.goal_oriented_knowledge_explorer import (
        GoalOrientedKnowledgeExplorer,
    )

    mock_invoke.return_value = {
        "knowledge_points": [
            {"name": "Core Rule", "role": "foundational", "solo_level": "beginner"},
            {"name": "Quick Use Case", "role": "practical", "solo_level": "beginner"},
            {"name": "Edge Case", "role": "foundational", "solo_level": "intermediate"},
        ]
    }

    explorer = GoalOrientedKnowledgeExplorer(MagicMock())
    output = explorer.explore(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Python Strings"},
            "session_adaptation_contract": {
                "perception": {"mode": "application_first"},
            },
        }
    )
    roles = [item["role"] for item in output["knowledge_points"]]
    assert roles == ["practical", "foundational", "foundational"]


@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.GoalOrientedKnowledgeExplorer.invoke")
def test_explorer_applies_theory_first_tie_break_order(mock_invoke):
    from modules.content_generator.agents.goal_oriented_knowledge_explorer import (
        GoalOrientedKnowledgeExplorer,
    )

    mock_invoke.return_value = {
        "knowledge_points": [
            {"name": "Immediate Example", "role": "practical", "solo_level": "beginner"},
            {"name": "Core Principle", "role": "foundational", "solo_level": "beginner"},
            {"name": "Practice Drill", "role": "practical", "solo_level": "intermediate"},
        ]
    }

    explorer = GoalOrientedKnowledgeExplorer(MagicMock())
    output = explorer.explore(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Python Strings"},
            "session_adaptation_contract": {
                "perception": {"mode": "theory_first"},
            },
        }
    )
    roles = [item["role"] for item in output["knowledge_points"]]
    assert roles == ["foundational", "practical", "practical"]
