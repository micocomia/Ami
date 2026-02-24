from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.documents import Document


def _deduplicate_sources(docs: List[Document]) -> List[Dict[str, Any]]:
    """Deduplicate retrieved sources by (file_name, lecture_number) key."""
    seen, sources = set(), []
    for doc in docs:
        key = (doc.metadata.get("file_name"), doc.metadata.get("lecture_number"))
        if key not in seen:
            seen.add(key)
            sources.append({
                k: v for k, v in doc.metadata.items()
                if k in ("file_name", "lecture_number", "content_category", "course_code", "page_number")
            })
    return sources
