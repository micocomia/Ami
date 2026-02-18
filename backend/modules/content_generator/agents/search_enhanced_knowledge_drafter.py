from __future__ import annotations

import ast
from typing import Any, Mapping, Optional, List
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, field_validator

from base import BaseAgent
from base.search_rag import SearchRagManager, format_docs
from modules.content_generator.prompts.search_enhanced_knowledge_drafter import (
    search_enhanced_knowledge_drafter_system_prompt,
    search_enhanced_knowledge_drafter_task_prompt,
)
from modules.content_generator.schemas import KnowledgeDraft
from config.loader import default_config


class KnowledgeDraftPayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    knowledge_points: Any
    knowledge_point: Any
    external_resources: str | None = ""
    visual_formatting_hints: str = ""
    processing_perception_hints: str = ""

    @field_validator("learner_profile", "learning_path", "learning_session", "knowledge_points", "knowledge_point")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class SearchEnhancedKnowledgeDrafter(BaseAgent):

    name: str = "SearchEnhancedKnowledgeDrafter"

    def __init__(self, model: Any, *, search_rag_manager: Optional[SearchRagManager] = None, use_search: bool = True):
        super().__init__(model=model, system_prompt=search_enhanced_knowledge_drafter_system_prompt, jsonalize_output=True)
        self.search_rag_manager = search_rag_manager or SearchRagManager.from_config(default_config)
        self.use_search = use_search

    def draft(self, payload: KnowledgeDraftPayload | Mapping[str, Any] | str):
        if not isinstance(payload, KnowledgeDraftPayload):
            payload = KnowledgeDraftPayload.model_validate(payload)
        data = payload.model_dump()
        # Optionally enrich external resources using the search RAG manager
        sources_used = []
        if self.use_search and self.search_rag_manager is not None:
            session = data.get("learning_session") or {}
            session_title = str(session.get("title", "")).strip() or "learning_session"
            knowledge_point = data.get("knowledge_point") or {}
            knowledge_point_name = str(knowledge_point.get('name', '')).strip()
            query = f"{session_title} {knowledge_point_name}".strip()
            docs = self.search_rag_manager.invoke_hybrid(query)
            # Collect detailed source references (ordered by same index as format_docs)
            for idx, doc in enumerate(docs):
                meta = doc.metadata or {}
                st = meta.get("source_type")
                if st == "verified_content":
                    ref = {
                        "source_type": "verified_content",
                        "course_code": meta.get("course_code", ""),
                        "course_name": meta.get("course_name", ""),
                        "lecture_number": meta.get("lecture_number"),
                        "page_number": meta.get("page_number"),
                        "file_name": meta.get("file_name", ""),
                    }
                elif st == "web_search":
                    ref = {
                        "source_type": "web_search",
                        "title": meta.get("title", ""),
                        "url": meta.get("source", ""),
                    }
                else:
                    ref = {"source_type": st or "unknown"}
                sources_used.append(ref)
            context = format_docs(docs)
            if context:
                ext = data.get("external_resources") or ""
                data["external_resources"] = f"{ext}{context}"
        raw_output = self.invoke(data, task_prompt=search_enhanced_knowledge_drafter_task_prompt)
        validated_output = KnowledgeDraft.model_validate(raw_output)
        result = validated_output.model_dump()
        if sources_used:
            result["sources_used"] = sources_used
        return result

def draft_knowledge_point_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    knowledge_points,
    knowledge_point,
    use_search: bool = True,
    visual_formatting_hints: str = "",
    processing_perception_hints: str = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    """Draft a single knowledge point using the agent, optionally enriching with a SearchRagManager."""
    drafter = SearchEnhancedKnowledgeDrafter(llm, search_rag_manager=search_rag_manager, use_search=use_search)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
        "knowledge_points": knowledge_points,
        "knowledge_point": knowledge_point,
        "visual_formatting_hints": visual_formatting_hints,
        "processing_perception_hints": processing_perception_hints,
    }
    return drafter.draft(payload)


def draft_knowledge_points_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    knowledge_points,
    allow_parallel: bool = True,
    use_search: bool = True,
    max_workers: int = 8,
    visual_formatting_hints: str = "",
    processing_perception_hints: str = "",
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
):
    """Draft multiple knowledge points in parallel or sequentially using the agent."""
    if isinstance(learning_session, str):
        learning_session = ast.literal_eval(learning_session)
    if isinstance(knowledge_points, str):
        knowledge_points = ast.literal_eval(knowledge_points)
    if search_rag_manager is None and use_search:
        search_rag_manager = SearchRagManager.from_config(default_config)
    def draft_one(kp):
        return draft_knowledge_point_with_llm(
            llm,
            learner_profile,
            learning_path,
            learning_session,
            knowledge_points,
            kp,
            use_search=use_search,
            visual_formatting_hints=visual_formatting_hints,
            processing_perception_hints=processing_perception_hints,
            search_rag_manager=search_rag_manager,
        )

    if allow_parallel:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(draft_one, knowledge_points))
    else:
        results: List[Any] = []
        for kp in knowledge_points:
            results.append(draft_one(kp))
        return results
