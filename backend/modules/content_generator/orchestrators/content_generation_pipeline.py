from __future__ import annotations

import ast
import json
import logging
from typing import Any, Callable, Mapping, Optional

from base.search_rag import SearchRagManager
from modules.content_generator.agents.document_quiz_generator import generate_document_quizzes_with_llm
from modules.content_generator.agents.goal_oriented_knowledge_explorer import explore_knowledge_points_with_llm
from modules.content_generator.agents.learning_document_integrator import (
    build_inline_assets_plan,
    integrate_learning_document_with_llm,
)
from modules.content_generator.agents.media_relevance_evaluator import filter_media_resources_with_llm
from modules.content_generator.agents.narrative_resource_generator import generate_narrative_resources_with_llm
from modules.content_generator.agents.podcast_style_converter import convert_to_podcast_with_llm
from modules.content_generator.agents.search_enhanced_knowledge_drafter import draft_knowledge_points_with_llm
from modules.content_generator.utils import (
    _FSLSM_MODERATE,
    _FSLSM_STRONG,
    collect_sources_used,
    find_media_resources,
    generate_tts_audio,
    get_fslsm_dim,
    get_fslsm_input,
    get_lightweight_llm,
    narrative_allowance,
    processing_perception_hints,
    understanding_hints,
    visual_formatting_hints,
)

logger = logging.getLogger(__name__)


JSONDict = dict[str, Any]


def _parse_jsonish(value: Any, default: Any):
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed
        except Exception:
            try:
                parsed = json.loads(value)
                return parsed
            except Exception:
                return default
    return value


def _extract_knowledge_points(raw_value: Any) -> list[dict]:
    """Normalize explorer output into a concrete list of knowledge-point dicts."""
    value = raw_value
    if isinstance(value, str):
        value = _parse_jsonish(value, {})
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass
    if isinstance(value, dict):
        kp = value.get("knowledge_points", [])
        if isinstance(kp, list):
            return [x for x in kp if isinstance(x, dict)]
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _extract_knowledge_drafts(raw_value: Any) -> list[dict]:
    """Normalize drafter output into a concrete list of draft dicts."""
    value = raw_value
    if isinstance(value, str):
        value = _parse_jsonish(value, [])
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            pass
    if isinstance(value, dict):
        kd = value.get("knowledge_drafts", [])
        if isinstance(kd, list):
            return [x for x in kd if isinstance(x, dict)]
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def generate_learning_content_with_llm(
    llm: Any,
    learner_profile: Any,
    learning_path: Any,
    learning_session: Any,
    *,
    allow_parallel: bool = True,
    with_quiz: bool = True,
    max_workers: int = 3,
    use_search: bool = True,
    output_markdown: bool = True,
    method_name: str = "ami",
    search_rag_manager: Optional[SearchRagManager] = None,
    quiz_mix_config: Optional[dict] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
    lightweight_llm: Any = None,
    evaluator: Optional[Callable[[Any, JSONDict], Mapping[str, Any]]] = None,
) -> JSONDict:
    """Unified learning content orchestration pipeline.

    Flow: explore -> draft -> media/narrative enrichment -> integrate -> audio -> quiz.
    """
    if method_name != "ami":
        raise ValueError("Unsupported method_name. Expected 'ami'.")

    learner_profile = _parse_jsonish(learner_profile, {})
    learning_path = _parse_jsonish(learning_path, {})
    learning_session = _parse_jsonish(learning_session, {})

    _lightweight_llm = get_lightweight_llm(llm, lightweight_llm)

    raw_knowledge_points = explore_knowledge_points_with_llm(
        llm,
        learner_profile,
        learning_path,
        learning_session,
    )
    knowledge_points = _extract_knowledge_points(raw_knowledge_points)

    fslsm_input = get_fslsm_input(learner_profile)
    fslsm_processing = get_fslsm_dim(learner_profile, "fslsm_processing")
    fslsm_perception = get_fslsm_dim(learner_profile, "fslsm_perception")
    fslsm_understanding = get_fslsm_dim(learner_profile, "fslsm_understanding")

    raw_knowledge_drafts = draft_knowledge_points_with_llm(
        llm,
        learner_profile,
        learning_path,
        learning_session,
        knowledge_points,
        goal_context=goal_context,
        allow_parallel=allow_parallel,
        use_search=use_search,
        max_workers=max_workers,
        visual_formatting_hints=visual_formatting_hints(fslsm_input),
        processing_perception_hints=processing_perception_hints(fslsm_processing, fslsm_perception),
        search_rag_manager=search_rag_manager,
    )
    knowledge_drafts = _extract_knowledge_drafts(raw_knowledge_drafts)

    sources_used = collect_sources_used(knowledge_drafts)

    media_resources = []
    narrative_resources = []
    inline_assets_plan = None
    session_title = learning_session.get("title", "") if isinstance(learning_session, dict) else ""

    max_videos, max_images, max_audio = 0, 0, 0
    if fslsm_input <= -_FSLSM_MODERATE:
        max_videos = 2 if fslsm_input <= -_FSLSM_STRONG else 1
        max_images = 2 if fslsm_input <= -_FSLSM_STRONG else 1
    elif fslsm_input >= _FSLSM_MODERATE:
        max_audio = 2 if fslsm_input >= _FSLSM_STRONG else 1

    if max_videos or max_images or max_audio:
        _search_runner = getattr(search_rag_manager, "search_runner", None) if search_rag_manager else None
        if _search_runner is None:
            try:
                from config.loader import default_config
                from base.searcher_factory import SearchRunner

                _search_runner = SearchRunner.from_config(default_config)
            except Exception:
                _search_runner = None

        if _search_runner is not None:
            try:
                media_resources = find_media_resources(
                    _search_runner,
                    knowledge_points,
                    max_videos=max_videos,
                    max_images=max_images,
                    max_audio=max_audio,
                    session_context=session_title,
                    video_focus="audio" if fslsm_input >= _FSLSM_MODERATE else "visual",
                )
            except Exception:
                media_resources = []

        if media_resources:
            kp_names = [kp.get("name", "") if isinstance(kp, dict) else str(kp) for kp in knowledge_points]
            media_resources = filter_media_resources_with_llm(
                llm,
                media_resources,
                session_title=session_title,
                knowledge_point_names=kp_names,
                lightweight_llm=_lightweight_llm,
            )

    verbal_narrative_allowance = narrative_allowance(fslsm_input)
    if verbal_narrative_allowance > 0:
        try:
            narrative_resources = generate_narrative_resources_with_llm(
                llm,
                knowledge_points,
                knowledge_drafts,
                session_title=session_title,
                max_narratives=verbal_narrative_allowance,
                include_tts=True,
                lightweight_llm=_lightweight_llm,
            )
        except Exception:
            narrative_resources = []

    if media_resources or narrative_resources:
        inline_assets_plan, inline_stats = build_inline_assets_plan(
            knowledge_points=knowledge_points,
            knowledge_drafts=knowledge_drafts,
            media_resources=media_resources,
            narrative_resources=narrative_resources,
            max_assets_per_subsection=2,
        )
    else:
        inline_stats = {"placed_assets": 0}

    learning_document = integrate_learning_document_with_llm(
        llm,
        learner_profile,
        learning_path,
        learning_session,
        knowledge_points,
        knowledge_drafts,
        output_markdown=output_markdown,
        media_resources=media_resources if media_resources else None,
        narrative_resources=narrative_resources if narrative_resources else None,
        inline_assets_plan=inline_assets_plan,
        understanding_hints=understanding_hints(fslsm_understanding),
    )

    content_format = "standard"
    if fslsm_input <= -_FSLSM_MODERATE:
        content_format = "visual_enhanced"
    elif fslsm_input >= _FSLSM_MODERATE:
        content_format = "audio_enhanced"

    audio_url = None
    audio_mode = None
    if fslsm_input >= _FSLSM_MODERATE:
        try:
            tts_source_document = learning_document
            if fslsm_input >= _FSLSM_STRONG:
                audio_mode = "host_expert_optional"
                tts_source_document = convert_to_podcast_with_llm(
                    llm,
                    learning_document,
                    learner_profile,
                    mode="full",
                )
            else:
                audio_mode = "narration_optional"

            audio_url = generate_tts_audio(tts_source_document)
        except Exception:
            audio_url = None

    learning_content: JSONDict = {
        "document": learning_document,
        "quizzes": {},
        "sources_used": sources_used,
        "content_format": content_format,
        "inline_assets_count": int((inline_stats or {}).get("placed_assets", 0)),
        "inline_assets_placement_stats": inline_stats or {},
    }
    if audio_mode is not None:
        learning_content["audio_mode"] = audio_mode
    if audio_url is not None:
        learning_content["audio_url"] = audio_url

    if with_quiz:
        if quiz_mix_config:
            from utils.quiz_scorer import get_quiz_mix_for_session as _get_quiz_mix

            session_dict = (
                learning_session
                if isinstance(learning_session, dict)
                else (learning_session.model_dump() if hasattr(learning_session, "model_dump") else {})
            )
            mix = _get_quiz_mix(session_dict, quiz_mix_config)
        else:
            mix = {
                "single_choice_count": 3,
                "multiple_choice_count": 0,
                "true_false_count": 0,
                "short_answer_count": 0,
                "open_ended_count": 0,
            }

        learning_content["quizzes"] = generate_document_quizzes_with_llm(
            llm,
            learner_profile,
            learning_document,
            single_choice_count=mix.get("single_choice_count", 3),
            multiple_choice_count=mix.get("multiple_choice_count", 0),
            true_false_count=mix.get("true_false_count", 0),
            short_answer_count=mix.get("short_answer_count", 0),
            open_ended_count=mix.get("open_ended_count", 0),
        )

    if evaluator is not None:
        try:
            _ = evaluator(_lightweight_llm, learning_content)
        except Exception as exc:
            logger.warning("Learning content evaluator hook failed: %s", exc)

    return learning_content
