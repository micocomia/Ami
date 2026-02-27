import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_get_lightweight_llm_prefers_explicit_instance():
    from modules.content_generator.utils.model_routing import get_lightweight_llm

    primary = MagicMock(name="primary")
    lightweight = MagicMock(name="lightweight")
    with patch("modules.content_generator.utils.model_routing.LLMFactory.create") as mock_create:
        selected = get_lightweight_llm(primary, lightweight)
    assert selected is lightweight
    mock_create.assert_not_called()


def test_get_lightweight_llm_falls_back_to_primary_on_error():
    from modules.content_generator.utils.model_routing import get_lightweight_llm

    primary = MagicMock(name="primary")
    with patch(
        "modules.content_generator.utils.model_routing.LLMFactory.create",
        side_effect=RuntimeError("mini unavailable"),
    ):
        selected = get_lightweight_llm(primary)
    assert selected is primary


@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.filter_media_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
def test_orchestrator_passes_lightweight_to_support_steps(
    mock_explore,
    mock_draft,
    mock_find_media,
    mock_filter_media,
    mock_narratives,
    mock_integrate,
    mock_quiz,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = [{"name": "Topic A", "type": "foundational"}]
    mock_draft.return_value = [{"title": "Draft A", "content": "Body"}]
    mock_find_media.return_value = [{"type": "audio", "title": "A", "audio_url": "u"}]
    mock_filter_media.return_value = []
    mock_narratives.return_value = []
    mock_integrate.return_value = "## Document\n\nBody"
    mock_quiz.return_value = {}

    primary = MagicMock(name="primary")
    lightweight = MagicMock(name="lightweight")
    search_rag_manager = MagicMock()
    search_rag_manager.search_runner = MagicMock()

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": 0.5,
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_understanding": 0.0,
            }
        }
    }

    generate_learning_content_with_llm(
        primary,
        profile,
        {},
        {"title": "Session A"},
        with_quiz=False,
        search_rag_manager=search_rag_manager,
        lightweight_llm=lightweight,
    )

    assert mock_filter_media.call_args.kwargs["lightweight_llm"] is lightweight
    assert mock_narratives.call_args.kwargs["lightweight_llm"] is lightweight
    assert mock_draft.call_args.kwargs["lightweight_llm"] is lightweight


@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.filter_media_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.get_lightweight_llm")
def test_orchestrator_uses_primary_when_lightweight_fallback_triggers(
    mock_get_lightweight,
    mock_explore,
    mock_draft,
    mock_find_media,
    mock_filter_media,
    mock_narratives,
    mock_integrate,
    mock_quiz,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = [{"name": "Topic A", "type": "foundational"}]
    mock_draft.return_value = [{"title": "Draft A", "content": "Body"}]
    mock_find_media.return_value = [{"type": "audio", "title": "A", "audio_url": "u"}]
    mock_filter_media.return_value = []
    mock_narratives.return_value = []
    mock_integrate.return_value = "## Document\n\nBody"
    mock_quiz.return_value = {}

    primary = MagicMock(name="primary")
    mock_get_lightweight.return_value = primary

    search_rag_manager = MagicMock()
    search_rag_manager.search_runner = MagicMock()

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_input": 0.5,
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_understanding": 0.0,
            }
        }
    }

    generate_learning_content_with_llm(
        primary,
        profile,
        {},
        {"title": "Session A"},
        with_quiz=False,
        search_rag_manager=search_rag_manager,
    )

    assert mock_filter_media.call_args.kwargs["lightweight_llm"] is primary
    assert mock_narratives.call_args.kwargs["lightweight_llm"] is primary
    assert mock_draft.call_args.kwargs["lightweight_llm"] is primary


@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_narrative_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.filter_media_resources_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.find_media_resources")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
def test_orchestrator_unwraps_explorer_dict_shape(
    mock_explore,
    mock_draft,
    mock_find_media,
    mock_filter_media,
    mock_narratives,
    mock_integrate,
    mock_quiz,
):
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    mock_explore.return_value = {"knowledge_points": [{"name": "Variables", "type": "foundational"}]}
    mock_draft.return_value = [{"title": "Variables", "content": "Body"}]
    mock_find_media.return_value = []
    mock_filter_media.return_value = []
    mock_narratives.return_value = []
    mock_integrate.return_value = "## Doc\n\nBody"
    mock_quiz.return_value = {}

    search_rag_manager = MagicMock()
    search_rag_manager.search_runner = MagicMock()

    profile = {
        "learning_preferences": {
            "fslsm_dimensions": {"fslsm_input": 0.0}
        }
    }

    generate_learning_content_with_llm(
        MagicMock(),
        profile,
        {},
        {"title": "Session A"},
        with_quiz=False,
        search_rag_manager=search_rag_manager,
    )

    # Fifth positional argument in draft_knowledge_points_with_llm is knowledge_points
    call_args = mock_draft.call_args.args
    assert isinstance(call_args[4], list)
    assert call_args[4] == [{"name": "Variables", "type": "foundational"}]
