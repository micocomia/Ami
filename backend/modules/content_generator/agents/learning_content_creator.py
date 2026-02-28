from __future__ import annotations

from typing import Any, Mapping, Optional

from pydantic import BaseModel

from base import BaseAgent
from base.search_rag import SearchRagManager
from modules.content_generator.prompts.learning_content_creator import (
    learning_content_creator_system_prompt,
    learning_content_creator_task_prompt_content,
    learning_content_creator_task_prompt_draft,
    learning_content_creator_task_prompt_outline,
)
from modules.content_generator.schemas import ContentOutline, KnowledgeDraft, LearningContent
from modules.content_generator.utils.fslsm_adaptation import (
    _FSLSM_MODERATE as FSLSM_MODERATE_CONST,
    _FSLSM_STRONG as FSLSM_STRONG_CONST,
    get_fslsm_dim,
    get_fslsm_input,
    narrative_allowance,
    processing_perception_hints,
    understanding_hints,
    visual_formatting_hints,
)


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


def prepare_content_outline_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    creator = LearningContentCreator(llm, search_rag_manager=search_rag_manager)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
    }
    return creator.prepare_outline(payload)


# Backward-compatible aliases for existing imports/tests.
_FSLSM_STRONG = FSLSM_STRONG_CONST
_FSLSM_MODERATE = FSLSM_MODERATE_CONST


def _get_fslsm_input(learner_profile) -> float:
    return get_fslsm_input(learner_profile)


def _get_fslsm_dim(learner_profile, dim_name: str) -> float:
    return get_fslsm_dim(learner_profile, dim_name)


def _processing_perception_hints(processing: float, perception: float) -> str:
    return processing_perception_hints(processing, perception)


def _understanding_hints(understanding: float) -> str:
    return understanding_hints(understanding)


def _visual_formatting_hints(fslsm_input: float) -> str:
    return visual_formatting_hints(fslsm_input)


def _narrative_allowance(fslsm_input: float) -> int:
    return narrative_allowance(fslsm_input)


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
    method_name="ami",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    quiz_mix_config: Optional[dict] = None,
    goal_context: Optional[Mapping[str, Any]] = None,
):
    """Backward-compatible wrapper around the content-generation orchestrator."""
    from modules.content_generator.orchestrators.content_generation_pipeline import (
        generate_learning_content_with_llm,
    )

    return generate_learning_content_with_llm(
        llm,
        learner_profile,
        learning_path,
        learning_session,
        allow_parallel=allow_parallel,
        with_quiz=with_quiz,
        max_workers=max_workers,
        use_search=use_search,
        output_markdown=output_markdown,
        method_name=method_name,
        search_rag_manager=search_rag_manager,
        quiz_mix_config=quiz_mix_config,
        goal_context=goal_context,
    )
