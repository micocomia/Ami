from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.content_generator.prompts.learning_content_creator import (
    learning_content_creator_system_prompt,
    learning_content_creator_task_prompt_content,
    learning_content_creator_task_prompt_draft,
    learning_content_creator_task_prompt_outline,
)
from modules.content_generator.schemas import ContentOutline, KnowledgeDraft, LearningContent


class ContentBasePayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    external_resources: str | None = ""


class ContentDraftPayload(ContentBasePayload):
    document_section: Any


class LearningContentCreator(BaseAgent):
    name: str = "LearningContentCreator"

    def __init__(self, model: Any, *, search_rag_manager: Optional[SearchRagManager] = None):
        super().__init__(model=model, system_prompt=learning_content_creator_system_prompt, jsonalize_output=True)
        self.search_rag_manager = search_rag_manager

    def prepare_outline(self, payload: ContentBasePayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentBasePayload):
            payload = ContentBasePayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_outline)
        validated_output = ContentOutline.model_validate(raw_output)
        return validated_output.model_dump()

    def draft_section(self, payload: ContentDraftPayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentDraftPayload):
            payload = ContentDraftPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_draft)
        validated_output = KnowledgeDraft.model_validate(raw_output)
        return validated_output.model_dump()

    def create_content(self, payload: ContentBasePayload | Mapping[str, Any] | str):
        if not isinstance(payload, ContentBasePayload):
            payload = ContentBasePayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=learning_content_creator_task_prompt_content)
        validated_output = LearningContent.model_validate(raw_output)
        return validated_output.model_dump()


def prepare_content_outline_with_llm(llm, learner_profile, learning_path, learning_session, *, search_rag_manager: Optional[SearchRagManager] = None):
    creator = LearningContentCreator(llm, search_rag_manager=search_rag_manager)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
    }
    return creator.prepare_outline(payload)


_FSLSM_STRONG = 0.7
_FSLSM_MODERATE = 0.3


def _get_fslsm_input(learner_profile) -> float:
    """Extract fslsm_input value from a learner profile dict. Returns 0.0 on missing/error."""
    if isinstance(learner_profile, str):
        try:
            import ast as _ast
            learner_profile = _ast.literal_eval(learner_profile)
        except Exception:
            return 0.0
    if not isinstance(learner_profile, dict):
        return 0.0
    try:
        dims = (
            learner_profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        if not isinstance(dims, dict):
            return 0.0
        val = dims.get("fslsm_input", 0.0)
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _get_fslsm_dim(learner_profile, dim_name: str) -> float:
    """Extract a named FSLSM dimension value from a learner profile dict. Returns 0.0 on missing/error."""
    if isinstance(learner_profile, str):
        try:
            import ast as _ast
            learner_profile = _ast.literal_eval(learner_profile)
        except Exception:
            return 0.0
    if not isinstance(learner_profile, dict):
        return 0.0
    try:
        dims = (
            learner_profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        if not isinstance(dims, dict):
            return 0.0
        val = dims.get(dim_name, 0.0)
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _processing_perception_hints(processing: float, perception: float) -> str:
    """Return per-section hints for the Processing and Perception FSLSM dimensions."""
    parts = []
    if processing <= -_FSLSM_MODERATE:
        parts.append(
            "**Processing Style (Active)**: After each concept, include a "
            "`🔧 Try It First` block — a hands-on challenge or trial-and-error simulation "
            "that lets the learner engage directly before the full explanation."
        )
    elif processing >= _FSLSM_MODERATE:
        parts.append(
            "**Processing Style (Reflective)**: After each concept, include a "
            "`🤔 Reflection Pause` block — one deep-thinking question that encourages "
            "the learner to connect the concept to prior knowledge before moving on."
        )
    if perception <= -_FSLSM_MODERATE:
        parts.append(
            "**Perception Style (Sensing)**: Present each concept in this order: "
            "(1) a concrete real-world example first, (2) step-by-step facts or procedure, "
            "(3) underlying theory last."
        )
    elif perception >= _FSLSM_MODERATE:
        parts.append(
            "**Perception Style (Intuitive)**: Present each concept in this order: "
            "(1) the abstract principle or theory first, (2) relationships and patterns, "
            "(3) concrete examples last."
        )
    if not parts:
        return ""
    return "\n\n**Learning Style Instructions**:\n" + "\n".join(f"- {p}" for p in parts)


def _understanding_hints(understanding: float) -> str:
    """Return document-level structure hint for the Understanding FSLSM dimension."""
    if understanding <= -_FSLSM_MODERATE:
        return (
            "\n\n**Understanding Style (Sequential)**: Structure the document with strict linear "
            "progression. Use explicit 'Building on [previous concept]...' transitions between "
            "sections. Avoid forward references — do not mention concepts before they have been "
            "introduced."
        )
    elif understanding >= _FSLSM_MODERATE:
        return (
            "\n\n**Understanding Style (Global)**: Begin the document with a `🗺️ Big Picture` "
            "section that shows how this session fits into the overall course and learning path. "
            "Use cross-references between sections to highlight connections between ideas."
        )
    return ""


def _visual_formatting_hints(fslsm_input: float) -> str:
    """Return formatting instruction hints for visual learners based on fslsm_input score."""
    if fslsm_input <= -_FSLSM_STRONG:
        return (
            "\n\n**Visual Formatting Instructions**: This learner is a strong visual learner. "
            "You MUST include at least one Mermaid diagram (```mermaid ... ```) to illustrate key concepts. "
            "Use markdown tables to present comparisons, steps, or structured data."
        )
    elif fslsm_input <= -_FSLSM_MODERATE:
        return (
            "\n\n**Visual Formatting Instructions**: This learner prefers visual content. "
            "Include markdown tables where applicable to present comparisons or structured data. "
            "Use code blocks and structured layouts where applicable."
        )
    return ""


def _narrative_allowance(fslsm_input: float) -> int:
    """Narrative inserts (short stories/poems) for verbal learners."""
    if fslsm_input >= _FSLSM_STRONG:
        return 3
    if fslsm_input >= _FSLSM_MODERATE:
        return 1
    return 0


def create_learning_content_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    document_outline=None,
    allow_parallel=True,
    with_quiz=True,
    max_workers=3,
    use_search=True,
    output_markdown=True,
    method_name="genmentor",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    quiz_mix_config: Optional[dict] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
):
    from .goal_oriented_knowledge_explorer import explore_knowledge_points_with_llm
    from .search_enhanced_knowledge_drafter import draft_knowledge_points_with_llm
    from .learning_document_integrator import (
        integrate_learning_document_with_llm,
        build_inline_assets_plan,
    )
    from .document_quiz_generator import generate_document_quizzes_with_llm

    if method_name == "genmentor":
        # 1. Explore knowledge points
        knowledge_points = explore_knowledge_points_with_llm(
            llm, learner_profile, learning_path, learning_session
        )

        # 2. Compute visual formatting hints based on fslsm_input
        fslsm_input = _get_fslsm_input(learner_profile)
        hints = _visual_formatting_hints(fslsm_input)

        # 2b. Extract remaining FSLSM dimensions and build their hints
        fslsm_processing = _get_fslsm_dim(learner_profile, "fslsm_processing")
        fslsm_perception = _get_fslsm_dim(learner_profile, "fslsm_perception")
        fslsm_understanding = _get_fslsm_dim(learner_profile, "fslsm_understanding")
        proc_perc_hints = _processing_perception_hints(fslsm_processing, fslsm_perception)
        und_hints = _understanding_hints(fslsm_understanding)

        # 3. Draft knowledge points with visual + processing/perception hints
        knowledge_drafts = draft_knowledge_points_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            goal_context=goal_context,
            allow_parallel=allow_parallel,
            use_search=use_search,
            max_workers=max_workers,
            visual_formatting_hints=hints,
            processing_perception_hints=proc_perc_hints,
            search_rag_manager=search_rag_manager,
        )

        # 4. Find media resources for visual and verbal learners
        media_resources = []
        narrative_resources = []
        inline_assets_plan = None
        session_title = learning_session.get("title", "") if isinstance(learning_session, dict) else ""
        max_videos, max_images, max_audio = 0, 0, 0
        if fslsm_input <= -_FSLSM_MODERATE:
            # Visual learner: fetch videos and images
            max_videos = 2 if fslsm_input <= -_FSLSM_STRONG else 1
            max_images = 2 if fslsm_input <= -_FSLSM_STRONG else 1
        elif fslsm_input >= _FSLSM_MODERATE:
            # Verbal learner: fetch Commons audio as supplementary to TTS podcast
            max_audio = 2 if fslsm_input >= _FSLSM_STRONG else 1

        if max_videos or max_images or max_audio:
            from .media_resource_finder import find_media_resources
            from .media_relevance_evaluator import filter_media_resources_with_llm
            _search_runner = None
            if search_rag_manager is not None:
                _search_runner = getattr(search_rag_manager, "search_runner", None)
            if _search_runner is None:
                try:
                    from config.loader import default_config
                    from base.searcher_factory import SearchRunner
                    _search_runner = SearchRunner.from_config(default_config)
                except Exception:
                    pass
            try:
                media_resources = find_media_resources(
                    _search_runner,
                    knowledge_points,
                    max_videos=max_videos,
                    max_images=max_images,
                    max_audio=max_audio,
                    session_context=session_title,
                )
            except Exception:
                media_resources = []
            if media_resources:
                kp_names = [kp.get("name", "") if isinstance(kp, dict) else str(kp) for kp in knowledge_points]
                media_resources = filter_media_resources_with_llm(
                    llm, media_resources, session_title=session_title, knowledge_point_names=kp_names
                )

        # 4b. Generate narrative resources (short stories/poems) for verbal learners.
        narrative_allowance = _narrative_allowance(fslsm_input)
        if narrative_allowance > 0:
            try:
                from .narrative_resource_generator import generate_narrative_resources_with_llm
                narrative_resources = generate_narrative_resources_with_llm(
                    llm,
                    knowledge_points,
                    knowledge_drafts,
                    session_title=session_title,
                    max_narratives=narrative_allowance,
                    include_tts=True,
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

        # 5. Integrate document (assets are injected inline inside sections)
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
            understanding_hints=und_hints,
        )

        # 6. Set content_format
        content_format = "standard"
        if fslsm_input <= -_FSLSM_MODERATE:
            content_format = "visual_enhanced"
        elif fslsm_input >= _FSLSM_MODERATE:
            content_format = "audio_enhanced"

        # 7. Optional host-expert listen mode for auditory learners (text remains canonical)
        audio_url = None
        audio_mode = None
        if fslsm_input >= _FSLSM_MODERATE:
            from .podcast_style_converter import convert_to_podcast_with_llm
            from .tts_generator import generate_tts_audio
            audio_mode = "host_expert_optional"
            try:
                host_expert_script = convert_to_podcast_with_llm(
                    llm, learning_document, learner_profile, mode="full"
                )
                audio_url = generate_tts_audio(host_expert_script)
            except Exception:
                audio_url = None

        learning_content = {
            "document": learning_document,
            "content_format": content_format,
            "inline_assets_count": int((inline_stats or {}).get("placed_assets", 0)),
            "inline_assets_placement_stats": inline_stats or {},
        }
        if audio_url is not None:
            learning_content["audio_url"] = audio_url
        if audio_mode is not None:
            learning_content["audio_mode"] = audio_mode

        if not with_quiz:
            return learning_content

        # 9. Generate quizzes (counts driven by session proficiency)
        if quiz_mix_config:
            from utils.quiz_scorer import get_quiz_mix_for_session as _get_quiz_mix
            _session_dict = (
                learning_session if isinstance(learning_session, dict)
                else (learning_session.model_dump() if hasattr(learning_session, "model_dump") else {})
            )
            _mix = _get_quiz_mix(_session_dict, quiz_mix_config)
        else:
            # Fallback defaults when no config provided
            _mix = {
                "single_choice_count": 3,
                "multiple_choice_count": 0,
                "true_false_count": 0,
                "short_answer_count": 0,
                "open_ended_count": 0,
            }

        document_quiz = generate_document_quizzes_with_llm(
            llm,
            learner_profile,
            learning_document,
            single_choice_count=_mix.get("single_choice_count", 3),
            multiple_choice_count=_mix.get("multiple_choice_count", 0),
            true_false_count=_mix.get("true_false_count", 0),
            short_answer_count=_mix.get("short_answer_count", 0),
            open_ended_count=_mix.get("open_ended_count", 0),
        )
        learning_content["quizzes"] = document_quiz
        return learning_content
    else:
        creator = LearningContentCreator(llm, search_rag_manager=search_rag_manager)
        if document_outline is None:
            document_outline = prepare_content_outline_with_llm(
                llm,
                learner_profile,
                learning_path,
                learning_session,
                search_rag_manager=search_rag_manager,
            )
        outline = document_outline if isinstance(document_outline, dict) else document_outline
        payload = {
            "learner_profile": learner_profile,
            "learning_path": learning_path,
            "learning_session": learning_session,
            "external_resources": "",
        }
        return creator.create_content(payload)
