import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@patch("modules.content_generator.orchestrators.content_generation_pipeline.evaluate_knowledge_draft_batch_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.evaluate_integrated_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
def test_orchestrator_retries_integrator_with_feedback(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = [{"name": "Branching", "role": "foundational", "solo_level": "beginner"}]
    mock_draft.return_value = [
        {
            "title": "Branching Basics",
            "content": (
                "## Branching Basics\n\n"
                "Branching controls program flow with conditions and decision paths.\n\n"
                "### Example\n\n"
                "A login system branches into success, retry, or lockout paths."
            ),
        }
    ]
    mock_draft_eval.return_value = {
        "evaluations": [
            {
                "draft_id": "draft-0",
                "is_acceptable": True,
                "issues": [],
                "improvement_directives": "",
            }
        ]
    }
    mock_integrate.side_effect = [
        "## Branching Basics\n\nInitial integration.",
        "## Branching Basics\n\nImproved integration.",
    ]
    mock_integrated_eval.side_effect = [
        {
            "is_acceptable": False,
            "issues": ["Transitions are abrupt."],
            "improvement_directives": "Tighten transitions between sections.",
            "repair_scope": "integrator_only",
            "affected_section_indices": [],
            "severity": "medium",
        },
        {
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
            "repair_scope": "integrator_only",
            "affected_section_indices": [],
            "severity": "low",
        },
    ]

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": 0.0,
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_understanding": 0.0,
            }
        }
    }

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        profile,
        {},
        {"title": "Session A"},
        with_quiz=False,
        use_search=False,
    )

    assert "Improved integration." in result["document"]
    assert mock_integrated_eval.call_count == 2
    assert mock_integrate.call_count == 2
    assert mock_integrate.call_args_list[1].kwargs["integration_feedback"] == "Tighten transitions between sections."


@patch("modules.content_generator.agents.media_relevance_evaluator.MediaRelevanceEvaluator.evaluate")
def test_media_evaluator_enriches_titles_and_descriptions(mock_eval):
    from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm

    mock_eval.return_value = {
        "relevance": [
            {
                "keep": True,
                "display_title": "Binary Search Walkthrough",
                "short_description": "Explains binary search decisions on a sorted list step by step.",
                "confidence": 0.88,
            }
        ]
    }
    resources = [
        {
            "type": "video",
            "title": "Binary Search Tutorial - YouTube",
            "snippet": "binary search algorithm on sorted arrays",
            "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
        }
    ]

    out = filter_media_resources_with_llm(
        llm=MagicMock(),
        resources=resources,
        session_title="Search Algorithms",
        knowledge_point_names=["Binary Search"],
        lightweight_llm=MagicMock(),
    )

    assert len(out) == 1
    assert out[0]["display_title"] == "Binary Search Walkthrough"
    assert "sorted list" in out[0]["short_description"]


@patch("modules.content_generator.agents.media_relevance_evaluator.LLMFactory.create", side_effect=RuntimeError("no mini"))
def test_media_fallback_adds_display_title_and_short_description(_mock_create):
    from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm

    resources = [
        {
            "type": "video",
            "title": "Quick Sort explained | YouTube",
            "snippet": "sorting algorithm walkthrough",
            "url": "https://www.youtube.com/watch?v=BBBBBBBBBBB",
        }
    ]
    out = filter_media_resources_with_llm(
        llm=None,
        resources=resources,
        session_title="Sorting Algorithms",
        knowledge_point_names=["Quick Sort"],
    )

    assert len(out) == 1
    assert out[0]["display_title"].startswith("Quick Sort")
    assert out[0]["short_description"]


def test_content_view_parser_ignores_h2_inside_code_fences():
    from utils.content_view import build_learning_content_view_model

    document = """# Demo

## First Topic
Intro paragraph.

```python
## Not a real heading
print("hello")
```

## First Topic
Second section body.
"""
    view = build_learning_content_view_model(document, [])

    assert len(view["sections"]) == 2
    assert view["sections"][0]["title"] == "First Topic"
    assert view["sections"][1]["title"] == "First Topic"
    assert "Not a real heading" in view["sections"][0]["markdown"]
    assert view["sections"][-1]["show_quiz_after"] is True


def test_section_to_draft_mapping_handles_duplicate_h2_titles():
    from modules.content_generator.agents.learning_document_integrator import map_integrated_sections_to_draft_ids

    document = """# Session

## Concept
Alpha explanation with condition checks.

## Concept
Beta explanation with loop counters.
"""
    draft_records = [
        {
            "draft_id": "draft-a",
            "knowledge_point": {"name": "Conditionals"},
            "draft": {"title": "Concept", "content": "Alpha explanation condition checks and branching."},
        },
        {
            "draft_id": "draft-b",
            "knowledge_point": {"name": "Loops"},
            "draft": {"title": "Concept", "content": "Beta explanation loop counters and iteration."},
        },
    ]

    mapping = map_integrated_sections_to_draft_ids(document, draft_records)
    assert mapping[0] == ["draft-a"]
    assert mapping[1] == ["draft-b"]


def test_deterministic_audit_rejects_narrative_only_section():
    from modules.content_generator.agents.knowledge_draft_evaluator import deterministic_knowledge_draft_audit

    draft = {
        "title": "Common French Phrases",
        "content": (
            "## Common French Phrases for Everyday Use\n\n"
            "#### Short Story: A Day in Paris\n\n"
            "Marie stepped off the train in Paris and used several phrases in daily conversation."
        ),
    }
    result = deterministic_knowledge_draft_audit(draft)
    assert result["is_acceptable"] is False
    assert any("instructional explanation" in issue.lower() for issue in result["issues"])


@patch("modules.content_generator.orchestrators.content_generation_pipeline.evaluate_knowledge_draft_batch_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.evaluate_integrated_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
def test_orchestrator_uses_shell_when_no_acceptable_drafts(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = [{"name": "Branching", "role": "foundational", "solo_level": "beginner"}]
    mock_draft.return_value = [{"title": "Branching", "content": "## Branching"}]
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": False, "issues": ["Too skeletal"], "improvement_directives": "Expand section."}
        ]
    }
    mock_integrate.return_value = "## Branching\n\nThis section is generated in best-effort mode."
    mock_integrated_eval.return_value = {
        "is_acceptable": True,
        "issues": [],
        "improvement_directives": "",
        "repair_scope": "integrator_only",
        "affected_section_indices": [],
        "severity": "low",
    }

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {"fslsm_input": 0.0, "fslsm_processing": 0.0, "fslsm_perception": 0.0}
        }
    }
    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        profile,
        {},
        {"title": "Session A"},
        with_quiz=False,
        use_search=False,
    )

    assert "best-effort mode" in result["document"].lower()
