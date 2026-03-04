from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager, format_docs

from .common import _truncate


class RetrieveVectorContextInput(BaseModel):
    query: str = Field(..., description="Query for vector retrieval.")
    top_k: int = Field(default=5, ge=1, le=12, description="Number of docs to retrieve.")
    max_chars: int = Field(default=2800, ge=500, le=8000, description="Maximum chars returned.")


def create_retrieve_vector_context_tool(search_rag_manager: Optional[SearchRagManager]):
    @tool("retrieve_vector_context", args_schema=RetrieveVectorContextInput)
    def retrieve_vector_context(query: str, top_k: int = 5, max_chars: int = 2800) -> str:
        """Retrieve context from vectorstore only (no web search, no vector writes)."""
        if search_rag_manager is None:
            return "Vector retrieval is unavailable."
        try:
            docs = search_rag_manager.retrieve(query, k=top_k)
        except Exception as exc:
            return f"Vector retrieval failed: {exc}"
        if not docs:
            return "No vector results found."
        return _truncate(format_docs(docs), max_chars)

    return retrieve_vector_context


__all__ = ["RetrieveVectorContextInput", "create_retrieve_vector_context_tool"]
