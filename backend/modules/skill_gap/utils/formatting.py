from __future__ import annotations

from typing import List

from langchain_core.documents import Document


def _format_retrieved_docs(docs: List[Document]) -> str:
    """Format retrieved documents into a string for LLM context."""
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs[:5], 1):
        header = f"[Source {i}: {doc.metadata.get('file_name', 'unknown')}]"
        parts.append(f"{header}\n{doc.page_content[:1000]}")
    return "\n\n".join(parts)
