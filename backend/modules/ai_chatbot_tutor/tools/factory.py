from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from base.search_rag import SearchRagManager

from .retrieve_session_learning_content_tool import create_retrieve_session_learning_content_tool
from .retrieve_vector_context_tool import create_retrieve_vector_context_tool
from .search_media_resources_tool import create_search_media_resources_tool
from .search_web_context_ephemeral_tool import create_search_web_context_ephemeral_tool
from .update_learning_preferences_from_signal_tool import (
    create_update_learning_preferences_from_signal_tool,
)


def create_ai_tutor_tools(
    *,
    search_rag_manager: Optional[SearchRagManager] = None,
    llm: Any = None,
    safe_preference_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    preference_update_sink: Optional[Dict[str, Any]] = None,
    preference_signal_classifier_llm: Optional[Any] = None,
    preference_signal_confidence_threshold: float = 0.6,
    enable_session_content: bool = True,
    enable_vector_retrieval: bool = True,
    enable_web_search: bool = True,
    enable_media_search: bool = True,
    enable_preference_updates: bool = True,
) -> List[Any]:
    tools: List[Any] = []

    if enable_session_content:
        tools.append(create_retrieve_session_learning_content_tool())
    if enable_vector_retrieval:
        tools.append(create_retrieve_vector_context_tool(search_rag_manager, sink=preference_update_sink))
    if enable_web_search:
        tools.append(create_search_web_context_ephemeral_tool(search_rag_manager, sink=preference_update_sink))
    if enable_media_search:
        tools.append(
            create_search_media_resources_tool(
                search_rag_manager=search_rag_manager,
                llm=llm,
                enable_llm_filter=True,
                sink=preference_update_sink,
            )
        )
    if enable_preference_updates:
        tools.append(
            create_update_learning_preferences_from_signal_tool(
                safe_update_fn=safe_preference_update_fn,
                sink=preference_update_sink,
                signal_classifier_llm=preference_signal_classifier_llm,
                signal_confidence_threshold=preference_signal_confidence_threshold,
            )
        )

    return tools


__all__ = ["create_ai_tutor_tools"]
