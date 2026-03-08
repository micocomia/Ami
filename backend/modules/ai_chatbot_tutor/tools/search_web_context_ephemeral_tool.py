from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager

from .common import _truncate


class SearchWebContextInput(BaseModel):
    query: str = Field(..., description="Query for web search.")
    top_k: int = Field(default=5, ge=1, le=10, description="Maximum web results.")
    max_chars: int = Field(default=2800, ge=500, le=8000, description="Maximum chars returned.")


def create_search_web_context_ephemeral_tool(search_rag_manager: Optional[SearchRagManager]):
    @tool("search_web_context_ephemeral", args_schema=SearchWebContextInput)
    def search_web_context_ephemeral(query: str, top_k: int = 5, max_chars: int = 2800) -> str:
        """Search web context without persisting documents into the shared vectorstore."""
        if search_rag_manager is None or search_rag_manager.search_runner is None:
            return "Web search is unavailable."
        try:
            results = search_rag_manager.search_runner.invoke(query)
        except Exception as exc:
            return f"Web search failed: {exc}"

        if not results:
            return "No web results found."

        blocks = []
        for idx, res in enumerate(results[:top_k], start=1):
            title = str(getattr(res, "title", "") or "Untitled")
            link = str(getattr(res, "link", "") or "")
            snippet = str(getattr(res, "snippet", "") or "")
            content = _truncate(str(getattr(res, "content", "") or ""), 700)
            block = (
                f"[{idx}] {title}\n"
                f"Source: {link}\n"
                f"Snippet: {snippet}\n"
                f"Content: {content}"
            )
            blocks.append(block)
        return _truncate("\n\n".join(blocks), max_chars)

    return search_web_context_ephemeral


__all__ = ["SearchWebContextInput", "create_search_web_context_ephemeral_tool"]
