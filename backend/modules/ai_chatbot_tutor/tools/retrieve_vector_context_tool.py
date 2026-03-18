from __future__ import annotations

from typing import Any, MutableMapping, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager, format_docs

from .common import (
    _document_to_trace_context,
    _record_contexts,
    _record_tool_call,
    _truncate,
)


class RetrieveVectorContextInput(BaseModel):
    query: str = Field(..., description="Query for vector retrieval.")
    top_k: int = Field(default=5, ge=1, le=12, description="Number of docs to retrieve.")
    max_chars: int = Field(default=2800, ge=500, le=8000, description="Maximum chars returned.")


def create_retrieve_vector_context_tool(
    search_rag_manager: Optional[SearchRagManager],
    sink: Optional[MutableMapping[str, Any]] = None,
):
    @tool("retrieve_vector_context", args_schema=RetrieveVectorContextInput)
    def retrieve_vector_context(query: str, top_k: int = 5, max_chars: int = 2800) -> str:
        """Retrieve context from vectorstore only (no web search, no vector writes)."""
        if search_rag_manager is None:
            _record_tool_call(
                sink,
                tool_name="retrieve_vector_context",
                query=query,
                status="unavailable",
                extra={"top_k": top_k, "max_chars": max_chars},
            )
            return "Vector retrieval is unavailable."
        try:
            docs = search_rag_manager.retrieve(query, k=top_k)
        except Exception as exc:
            _record_tool_call(
                sink,
                tool_name="retrieve_vector_context",
                query=query,
                status="error",
                extra={"top_k": top_k, "max_chars": max_chars, "error": str(exc)},
            )
            return f"Vector retrieval failed: {exc}"
        if not docs:
            _record_tool_call(
                sink,
                tool_name="retrieve_vector_context",
                query=query,
                status="empty",
                extra={"top_k": top_k, "max_chars": max_chars},
            )
            return "No vector results found."
        _record_tool_call(
            sink,
            tool_name="retrieve_vector_context",
            query=query,
            status="ok",
            result_count=len(docs),
            extra={"top_k": top_k, "max_chars": max_chars},
        )
        _record_contexts(
            sink,
            tool_name="retrieve_vector_context",
            query=query,
            contexts=[_document_to_trace_context(doc) for doc in docs],
        )
        return _truncate(format_docs(docs), max_chars)

    return retrieve_vector_context


__all__ = ["RetrieveVectorContextInput", "create_retrieve_vector_context_tool"]
