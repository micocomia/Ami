from __future__ import annotations

import ast
from typing import Any


def _source_dedup_key(source_ref: Any) -> tuple:
    if isinstance(source_ref, dict):
        st = source_ref.get("source_type", "")
        if st == "verified_content":
            return (st, source_ref.get("file_name", ""), source_ref.get("page_number", ""))
        if st == "web_search":
            return (st, source_ref.get("url", ""))
        return (st, source_ref.get("page_content", "")[:120])
    return (str(source_ref),)


def collect_sources_used(knowledge_drafts: Any) -> list[dict]:
    """Collect unique source references across all knowledge drafts."""
    if isinstance(knowledge_drafts, str):
        try:
            knowledge_drafts = ast.literal_eval(knowledge_drafts)
        except Exception:
            return []

    if not isinstance(knowledge_drafts, list):
        return []

    sources: list[dict] = []
    seen_keys = set()
    for draft in knowledge_drafts:
        if not isinstance(draft, dict):
            continue
        draft_sources = draft.get("sources_used") or []
        if not isinstance(draft_sources, list):
            continue
        for source_ref in draft_sources:
            key = _source_dedup_key(source_ref)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if isinstance(source_ref, dict):
                sources.append(source_ref)
            else:
                sources.append({"source_type": "unknown", "value": str(source_ref)})
    return sources
