import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Helpers ──────────────────────────────────────────────────────────────────

_PIPELINE = "modules.content_generator.orchestrators.content_generation_pipeline"
_MOCK_INTEGRATE = f"{_PIPELINE}.integrate_learning_document_with_llm"
_MOCK_INTEGRATE_PARALLEL = f"{_PIPELINE}.integrate_learning_document_parallel"
_MOCK_EXPLORE = f"{_PIPELINE}.explore_knowledge_points_with_llm"
_MOCK_DRAFT = f"{_PIPELINE}.draft_knowledge_points_with_llm"
_MOCK_DRAFT_ONE = f"{_PIPELINE}.draft_knowledge_point_with_llm"
_MOCK_INTEGRATED_EVAL = f"{_PIPELINE}.evaluate_integrated_document_with_llm"
_MOCK_DRAFT_EVAL = f"{_PIPELINE}.evaluate_knowledge_draft_batch_with_llm"

_NEUTRAL_PROFILE = {
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_input": 0.0,
            "fslsm_processing": 0.0,
            "fslsm_perception": 0.0,
            "fslsm_understanding": 0.0,
        }
    }
}

_PASSING_EVAL = {
    "is_acceptable": True,
    "issues": [],
    "improvement_directives": "",
    "repair_scope": "integrator_only",
    "affected_section_indices": [],
    "severity": "low",
}

_SINGLE_KP = [{"name": "Branching", "role": "foundational", "solo_level": "beginner"}]
_SINGLE_SECTION_CONTENT = (
    "## Branching Basics\n\n"
    "Branching controls program flow with conditions and decision paths.\n\n"
    "### Example\n\n"
    "A login system branches into success, retry, or lockout paths."
)

# Two-KP content that reliably passes the deterministic audit
_TWO_KP_DRAFTS = [
    {
        "title": "Foundations",
        "content": (
            "## Foundations\n\n"
            "Detailed instructional prose for the first concept with concrete examples and clear rationale."
        ),
    },
    {
        "title": "Applications",
        "content": (
            "## Applications\n\n"
            "Detailed instructional prose for the second concept with applied steps and practical outcomes."
        ),
    },
]
_TWO_KPS = [
    {"name": "Foundations", "role": "foundational", "solo_level": "beginner"},
    {"name": "Applications", "role": "practical", "solo_level": "intermediate"},
]


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
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

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
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
        "## Branching Basics\n\nInitial integration with complete instructional prose that explains branching decisions clearly.",
        "## Branching Basics\n\nImproved integration with stronger transitions and clearer progression between ideas.",
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
        _PASSING_EVAL,
    ]

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session A"},
        with_quiz=False,
        use_search=False,
    )

    assert "Improved integration" in result["document"]
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
        fast_llm=MagicMock(),
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


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
@patch(_MOCK_DRAFT_ONE)
def test_no_progress_quality_loop_exits_early(
    mock_repair,
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = [{"name": "Topic A", "role": "foundational", "solo_level": "beginner"}]
    mock_repair.return_value = {"title": "Topic A", "content": _SINGLE_SECTION_CONTENT}
    mock_draft.return_value = [
        {
            "title": "Topic A",
            "content": _SINGLE_SECTION_CONTENT,
        }
    ]
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }
    document_body = "## Topic A\n\nEnough prose here to satisfy deterministic checks for this section.\n"
    mock_integrate.return_value = document_body

    # Same failing eval returned every round — identical fingerprint, should exit after round 2
    identical_eval = {
        "is_acceptable": False,
        "issues": ["Section lacks depth."],
        "improvement_directives": "Add more detail.",
        "repair_scope": "integrator_only",
        "affected_section_indices": [],
        "severity": "medium",
    }
    mock_integrated_eval.return_value = identical_eval

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session B"},
        with_quiz=False,
        use_search=False,
    )

    # Integration evaluator called twice (rounds 1 and 2), then no-progress exit
    assert mock_integrated_eval.call_count == 2
    # integrate called: initial + 1 integrator_only retry (before no-progress detected on round 2)
    assert mock_integrate.call_count == 2
    assert result["document"] == document_body


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
@patch(_MOCK_DRAFT_ONE)
def test_parallel_draft_repair_runs_all_failed_drafts(
    mock_repair_fn,
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    """Parallel draft repair should call draft_knowledge_point_with_llm for every failed draft."""
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    kps = [
        {"name": "Topic A", "role": "foundational", "solo_level": "beginner"},
        {"name": "Topic B", "role": "supporting", "solo_level": "beginner"},
        {"name": "Topic C", "role": "supporting", "solo_level": "beginner"},
    ]
    mock_explore.return_value = kps

    section_template = "## {title}\n\nEnough prose for deterministic check — detailed explanation here.\n"
    mock_draft.return_value = [{"title": kp["name"], "content": section_template.format(title=kp["name"])} for kp in kps]

    # All drafts fail eval → triggers targeted repair for all 3
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": f"draft-{i}", "is_acceptable": False, "issues": ["Weak"], "improvement_directives": "Expand."}
            for i in range(3)
        ]
    }

    # Repair returns a better draft
    def _repair(*_args, **_kwargs):
        kp = _kwargs.get("knowledge_point", {})
        return {"title": kp.get("name", "Fixed"), "content": section_template.format(title=kp.get("name", "Fixed"))}

    mock_repair_fn.side_effect = _repair

    integrated_doc = "\n".join(section_template.format(title=kp["name"]) for kp in kps)
    mock_integrate.return_value = integrated_doc
    mock_integrated_eval.return_value = _PASSING_EVAL

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session C"},
        with_quiz=False,
        use_search=False,
    )

    # All 3 failed drafts must have been repaired
    assert mock_repair_fn.call_count == 3
    assert all(call.kwargs.get("use_search") is False for call in mock_repair_fn.call_args_list)
    assert "document" in result


@patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.filter_media_resources_with_llm")
@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_draft_terminal_failure_still_runs_required_stages(
    mock_explore,
    mock_draft,
    mock_repair_fn,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
    mock_filter_media,
    mock_find_media,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    kps = [
        {"name": "Topic A", "role": "foundational", "solo_level": "beginner"},
        {"name": "Topic B", "role": "supporting", "solo_level": "beginner"},
        {"name": "Topic C", "role": "supporting", "solo_level": "beginner"},
    ]
    prose = "## {title}\n\nEnough instructional prose for deterministic checks."
    mock_explore.return_value = kps
    mock_draft.return_value = [{"title": kp["name"], "content": prose.format(title=kp["name"])} for kp in kps]
    mock_repair_fn.side_effect = lambda *_args, **kwargs: {
        "title": kwargs.get("knowledge_point", {}).get("name", "X"),
        "content": prose.format(title=kwargs.get("knowledge_point", {}).get("name", "X")),
    }
    # Keep acceptance ratio below threshold even after one repair pass.
    mock_draft_eval.side_effect = [
        {
            "evaluations": [
                {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
                {"draft_id": "draft-1", "is_acceptable": False, "issues": ["Weak"], "improvement_directives": "Expand."},
                {"draft_id": "draft-2", "is_acceptable": False, "issues": ["Weak"], "improvement_directives": "Expand."},
            ]
        },
        {
            "evaluations": [
                {"draft_id": "draft-1", "is_acceptable": False, "issues": ["Still weak"], "improvement_directives": "Expand more."},
                {"draft_id": "draft-2", "is_acceptable": False, "issues": ["Still weak"], "improvement_directives": "Expand more."},
            ]
        },
    ]
    mock_integrate.return_value = "## Topic A\n\nIntegrated best-effort content."
    mock_integrated_eval.return_value = _PASSING_EVAL
    mock_find_media.return_value = []
    mock_filter_media.return_value = []

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": -0.8,
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
        {"title": "Session Fast Exit"},
        with_quiz=False,
        search_rag_manager=MagicMock(search_runner=MagicMock()),
        use_search=True,
    )

    assert mock_integrate.call_count == 1
    assert mock_integrated_eval.call_count == 1
    assert mock_find_media.call_count == 1
    assert "Integrated best-effort content" in result["document"]


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_conditional_draft_llm_eval_skips_low_risk_drafts(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
    mock_integrate.return_value = "## Branching Basics\n\nIntegrated low-risk content."
    mock_integrated_eval.return_value = _PASSING_EVAL
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Low Risk"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_draft_eval.call_count == 0
    assert mock_integrate.call_count == 1


@patch("modules.content_generator.orchestrators.content_generation_pipeline.filter_media_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_conditional_draft_llm_eval_runs_for_contract_risk(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
    mock_find_media,
    mock_filter_media,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [
        {
            "title": "Branching Basics",
            "content": _SINGLE_SECTION_CONTENT,
        }
    ]
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }
    mock_integrate.return_value = "## Branching Basics\n\nIntegrated content."
    mock_integrated_eval.return_value = _PASSING_EVAL
    mock_find_media.return_value = []
    mock_filter_media.return_value = []

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": -0.8,
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_understanding": 0.0,
            }
        }
    }

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        profile,
        {},
        {"title": "Session Visual Risk"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_draft_eval.call_count >= 1


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_conditional_draft_llm_eval_runs_for_advanced_depth_risk(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    advanced_kp = [{"name": "Optimization Tradeoffs", "role": "practical", "solo_level": "intermediate"}]
    mock_explore.return_value = advanced_kp
    mock_draft.return_value = [
        {
            "title": "Optimization Tradeoffs",
            "content": (
                "## Optimization Tradeoffs\n\n"
                "Optimization balances execution cost, maintainability, and correctness in practical systems with "
                "concrete tradeoffs, implementation constraints, and evidence-driven decisions."
            ),
        }
    ]
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }
    mock_integrate.return_value = "## Optimization Tradeoffs\n\nIntegrated content."
    mock_integrated_eval.return_value = _PASSING_EVAL

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Advanced Risk"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_draft_eval.call_count == 1


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_final_evaluator_retries_once_on_transient_error(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }
    mock_integrate.return_value = "## Branching Basics\n\nIntegrated content."
    mock_integrated_eval.side_effect = [RuntimeError("temporary"), _PASSING_EVAL]

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Retry"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_integrated_eval.call_count == 2
    assert mock_integrate.call_count == 1
    assert "Integrated content" in result["document"]


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_non_safety_contract_issues_soft_fail_without_retry(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
    mock_draft_eval.return_value = {
        "evaluations": [{"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}]
    }
    mock_integrate.return_value = "## Branching Basics\n\nIntegrated content."
    mock_integrated_eval.return_value = {
        "is_acceptable": False,
        "issues": [
            "There are no Mermaid diagrams or tables present, which is required for the strong visual input mode.",
            "The checkpoint challenges are present but could be better integrated for the processing mode.",
        ],
        "improvement_directives": "Add Mermaid/table and improve checkpoint placement.",
        "repair_scope": "integrator_only",
        "affected_section_indices": [],
        "severity": "medium",
    }

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": -0.8,
                "fslsm_processing": -0.8,
                "fslsm_perception": 0.0,
                "fslsm_understanding": 0.0,
            }
        }
    }
    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        profile,
        {},
        {"title": "Session Soft Contract"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_integrated_eval.call_count == 1
    assert mock_integrate.call_count == 1
    assert "Integrated content" in result["document"]


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_draft_targeted_repair_uses_search_for_factual_gaps(
    mock_explore,
    mock_draft,
    mock_repair,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
    mock_repair.return_value = {"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}
    mock_draft_eval.side_effect = [
        {
            "evaluations": [
                {
                    "draft_id": "draft-0",
                    "is_acceptable": False,
                    "issues": ["The claim needs source support."],
                    "improvement_directives": "Add citations and verify factual accuracy with sources.",
                }
            ]
        },
        {
            "evaluations": [
                {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}
            ]
        },
    ]
    mock_integrate.return_value = "## Branching Basics\n\nIntegrated content."
    mock_integrated_eval.return_value = _PASSING_EVAL

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_input": -0.8,
                    "fslsm_processing": 0.0,
                    "fslsm_perception": 0.0,
                    "fslsm_understanding": 0.0,
                }
            }
        },
        {},
        {"title": "Session Factual Repair"},
        with_quiz=False,
        use_search=True,
    )

    assert mock_repair.call_count == 1
    assert mock_repair.call_args.kwargs["use_search"] is True


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
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

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching", "content": "## Branching"}]
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": False, "issues": ["Too skeletal"], "improvement_directives": "Expand section."}
        ]
    }
    mock_integrate.return_value = "## Branching\n\nThis section is generated in best-effort mode."
    mock_integrated_eval.return_value = _PASSING_EVAL

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


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_quality_loop_applies_targeted_section_redraft_once(
    mock_explore,
    mock_draft,
    mock_redraft_one,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    """When evaluator returns section_redraft, pipeline redrafts only affected drafts once, then reintegrates."""
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _TWO_KPS
    mock_draft.return_value = _TWO_KP_DRAFTS
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
            {"draft_id": "draft-1", "is_acceptable": True, "issues": [], "improvement_directives": ""},
        ]
    }

    prose = "Detailed instructional prose for concept with concrete examples and clear rationale."
    initial_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\n{prose}"
    improved_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\nImproved second section with stronger depth."
    mock_integrate.side_effect = [initial_doc, improved_doc]
    mock_redraft_one.return_value = {
        "title": "Applications",
        "content": (
            "## Applications\n\n"
            "Revised instructional prose for applications with clearer depth and examples."
        ),
    }
    mock_integrated_eval.side_effect = [
        {
            "is_acceptable": False,
            "issues": ["Section 1 needs clearer instructional depth."],
            "improvement_directives": "Improve depth of section 1.",
            "repair_scope": "section_redraft",
            "affected_section_indices": [1],
            "severity": "medium",
        },
        _PASSING_EVAL,
    ]

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Fix5"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_redraft_one.call_count == 1
    assert mock_redraft_one.call_args.kwargs["use_search"] is False
    assert mock_integrate.call_count == 2
    assert "Improved second section" in result["document"]
    assert mock_integrate.call_args_list[1].kwargs["integration_feedback"] == "Improve depth of section 1."


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_quality_loop_revalidates_targeted_redraft_before_reintegration(
    mock_explore,
    mock_draft,
    mock_redraft_one,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _TWO_KPS
    mock_draft.return_value = _TWO_KP_DRAFTS
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
            {"draft_id": "draft-1", "is_acceptable": True, "issues": [], "improvement_directives": ""},
        ]
    }
    prose = "Detailed instructional prose for concept with concrete examples and clear rationale."
    initial_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\n{prose}"
    retry_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\nRetry integration still uses validated drafts."
    mock_integrate.side_effect = [initial_doc, retry_doc]
    mock_redraft_one.return_value = {"title": "Applications", "content": "## Applications"}
    mock_integrated_eval.side_effect = [
        {
            "is_acceptable": False,
            "issues": ["Section 1 needs clearer instructional depth."],
            "improvement_directives": "Improve depth of section 1.",
            "repair_scope": "section_redraft",
            "affected_section_indices": [1],
            "severity": "medium",
        },
        _PASSING_EVAL,
    ]

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Revalidate Redraft"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_redraft_one.call_count == 1
    assert mock_draft_eval.call_count == 1
    assert mock_integrate.call_count == 2
    assert mock_integrate.call_args_list[1].kwargs["knowledge_drafts"][1]["content"] == _TWO_KP_DRAFTS[1]["content"]
    assert "Retry integration still uses validated drafts" in result["document"]


@patch("modules.content_generator.orchestrators.content_generation_pipeline.map_integrated_sections_to_draft_ids")
@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_quality_loop_parallelizes_multiple_targeted_redrafts(
    mock_explore,
    mock_draft,
    mock_redraft_one,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
    mock_map_sections,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _TWO_KPS
    mock_draft.return_value = _TWO_KP_DRAFTS
    mock_draft_eval.side_effect = [
        {
            "evaluations": [
                {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
                {"draft_id": "draft-1", "is_acceptable": True, "issues": [], "improvement_directives": ""},
            ]
        },
        {
            "evaluations": [
                {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
                {"draft_id": "draft-1", "is_acceptable": True, "issues": [], "improvement_directives": ""},
            ]
        },
    ]
    prose = "Detailed instructional prose for concept with concrete examples and clear rationale."
    initial_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\n{prose}"
    revised_doc = (
        "## Foundations\n\nImproved foundations.\n\n"
        "## Applications\n\nImproved applications."
    )
    mock_integrate.side_effect = [initial_doc, revised_doc]
    mock_map_sections.return_value = {0: ["draft-0"], 1: ["draft-1"]}
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()

    def _parallel_redraft(*_args, **kwargs):
        with state_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        time.sleep(0.05)
        with state_lock:
            state["active"] -= 1
        title = kwargs.get("knowledge_point", {}).get("name", "Updated")
        return {
            "title": title,
            "content": (
                f"## {title}\n\n"
                f"Revised instructional prose for {title.lower()} with clearer depth, applied examples, and explicit reasoning."
            ),
        }

    mock_redraft_one.side_effect = _parallel_redraft
    mock_integrated_eval.side_effect = [
        {
            "is_acceptable": False,
            "issues": ["Section 0 needs clearer instructional depth.", "Section 1 needs clearer instructional depth."],
            "improvement_directives": "Improve depth of sections 0 and 1.",
            "repair_scope": "section_redraft",
            "affected_section_indices": [0, 1],
            "severity": "medium",
        },
        _PASSING_EVAL,
    ]

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Parallel Redraft"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_redraft_one.call_count == 2
    assert state["max_active"] > 1
    assert mock_draft_eval.call_count == 2
    assert mock_integrate.call_count == 2


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT_ONE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_section_redraft_is_capped_to_one_round(
    mock_explore,
    mock_draft,
    mock_redraft_one,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _TWO_KPS
    mock_draft.return_value = _TWO_KP_DRAFTS
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""},
            {"draft_id": "draft-1", "is_acceptable": True, "issues": [], "improvement_directives": ""},
        ]
    }
    prose = "Detailed instructional prose for concept with concrete examples and clear rationale."
    initial_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\n{prose}"
    revised_doc = f"## Foundations\n\n{prose}\n\n## Applications\n\nRevised prose after targeted redraft."
    mock_integrate.side_effect = [initial_doc, revised_doc]
    mock_redraft_one.return_value = {"title": "Applications", "content": revised_doc}
    mock_integrated_eval.side_effect = [
        {
            "is_acceptable": False,
            "issues": ["Section needs more depth."],
            "improvement_directives": "Increase depth.",
            "repair_scope": "section_redraft",
            "affected_section_indices": [1],
            "severity": "medium",
        },
        {
            "is_acceptable": False,
            "issues": ["Section still needs more depth."],
            "improvement_directives": "Increase depth.",
            "repair_scope": "section_redraft",
            "affected_section_indices": [1],
            "severity": "medium",
        },
    ]

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Redraft Cap"},
        with_quiz=False,
        use_search=False,
    )

    assert mock_redraft_one.call_count == 1
    assert mock_integrate.call_count == 2


def test_integrator_prompts_require_citation_marker_preservation():
    from modules.content_generator.prompts.learning_document_integrator import (
        integrated_document_generator_system_prompt,
        section_synthesis_system_prompt,
    )

    assert "Do NOT renumber, delete, or invent citation markers" in integrated_document_generator_system_prompt
    assert "Do NOT renumber, remove, or invent citation markers" in section_synthesis_system_prompt


@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_INTEGRATE)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_knowledge_points_capped_at_four(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_integrated_eval,
    mock_draft_eval,
):
    """Fix 4: pipeline must cap knowledge points to _MAX_KNOWLEDGE_POINTS (4) after explorer returns."""
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    # Explorer returns 6 KPs — pipeline should cap to 4
    kps_6 = [
        {"name": f"Topic {i}", "role": "foundational", "solo_level": "beginner"}
        for i in range(6)
    ]
    mock_explore.return_value = kps_6

    prose = "Enough instructional prose for deterministic check — detailed explanation here.\n"
    # Return only 4 drafts (matching the capped list)
    mock_draft.return_value = [
        {"title": f"Topic {i}", "content": f"## Topic {i}\n\n{prose}"}
        for i in range(4)
    ]
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": f"draft-{i}", "is_acceptable": True, "issues": [], "improvement_directives": ""}
            for i in range(4)
        ]
    }
    doc = "\n\n".join(f"## Topic {i}\n\n{prose}" for i in range(4))
    mock_integrate.return_value = doc
    mock_integrated_eval.return_value = _PASSING_EVAL

    generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Cap"},
        with_quiz=False,
        use_search=False,
    )

    # Verify draft_knowledge_points_with_llm was called with at most 4 KPs
    assert mock_draft.called
    drafted_kps = mock_draft.call_args.kwargs.get("knowledge_points", [])
    assert len(drafted_kps) <= 4, f"Expected at most 4 KPs drafted, got {len(drafted_kps)}"


@patch(_MOCK_INTEGRATE_PARALLEL)
@patch(_MOCK_DRAFT_EVAL)
@patch(_MOCK_INTEGRATED_EVAL)
@patch(_MOCK_DRAFT)
@patch(_MOCK_EXPLORE)
def test_pipeline_routes_to_parallel_when_fast_llm_is_distinct(
    mock_explore,
    mock_draft,
    mock_integrated_eval,
    mock_draft_eval,
    mock_integrate_parallel,
):
    """Fix 3: when a distinct fast_llm is passed, pipeline routes to integrate_learning_document_parallel."""
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = _SINGLE_KP
    mock_draft.return_value = [{"title": "Branching Basics", "content": _SINGLE_SECTION_CONTENT}]
    mock_draft_eval.return_value = {
        "evaluations": [
            {"draft_id": "draft-0", "is_acceptable": True, "issues": [], "improvement_directives": ""}
        ]
    }
    parallel_doc = "## Branching Basics\n\nParallel integration output."
    mock_integrate_parallel.return_value = parallel_doc
    mock_integrated_eval.return_value = _PASSING_EVAL

    result = generate_learning_content_with_llm(
        MagicMock(name="primary"),
        _NEUTRAL_PROFILE,
        {},
        {"title": "Session Parallel"},
        with_quiz=False,
        use_search=False,
        fast_llm=MagicMock(name="fast"),  # distinct fast_llm → parallel path
    )

    # Parallel path should be taken
    assert mock_integrate_parallel.call_count >= 1
    assert "Parallel integration" in result["document"]


def test_deterministic_integrated_audit_rejects_excess_h2_sections():
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        _deterministic_integrated_section_audit,
    )

    document = """# Session

## Foundations
Intro teaching content with concrete examples and explanation details.

## Applications
Applied teaching content with guided steps and reasoning.

## Extra Scaffold
This should not be an extra core section.
"""
    result = _deterministic_integrated_section_audit(document, expected_core_sections=2)
    assert result["is_acceptable"] is False
    assert result["repair_scope"] == "integrator_only"
    assert any("Core section count mismatch" in issue for issue in result["issues"])
