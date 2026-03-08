from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .common import _message_tokens_overlap_score, _section_snippet, _truncate
from utils import store


class RetrieveSessionLearningContentInput(BaseModel):
    query: str = Field(..., description="Learner query for session clarification.")
    user_id: Optional[str] = Field(default=None, description="Current user ID.")
    goal_id: Optional[int] = Field(default=None, description="Current goal ID.")
    session_index: Optional[int] = Field(default=None, description="Current active session index.")
    top_k: int = Field(default=3, ge=1, le=8, description="Maximum snippets to return.")
    max_chars: int = Field(default=2800, ge=500, le=8000, description="Maximum total chars returned.")


def _extract_doc_snippet(
    *,
    user_id: str,
    goal_id: int,
    session_index: int,
    record: Mapping[str, Any],
    query: str,
    per_doc_chars: int,
) -> Optional[Dict[str, Any]]:
    if not isinstance(record, Mapping):
        return None
    payload = record.get("learning_content")
    if not isinstance(payload, Mapping):
        return None
    document = str(payload.get("document", "") or "").strip()
    if not document:
        return None

    snippet = _section_snippet(document, query, max_chars=per_doc_chars)
    title = f"session_index={session_index}"
    score = _message_tokens_overlap_score(snippet, query)
    return {
        "title": title,
        "score": score,
        "source": f"learning_content:{user_id}:{goal_id}:{session_index}",
        "snippet": snippet,
        "session_index": session_index,
    }


def _collect_session_indices(user_id: str, goal_id: int) -> List[int]:
    goal = store.get_goal(user_id, goal_id) or {}
    learning_path = goal.get("learning_path", [])
    if not isinstance(learning_path, list):
        return []
    return [idx for idx, session in enumerate(learning_path) if isinstance(session, Mapping)]


def create_retrieve_session_learning_content_tool():
    @tool("retrieve_session_learning_content", args_schema=RetrieveSessionLearningContentInput)
    def retrieve_session_learning_content(
        query: str,
        user_id: Optional[str] = None,
        goal_id: Optional[int] = None,
        session_index: Optional[int] = None,
        top_k: int = 3,
        max_chars: int = 2800,
    ) -> str:
        """Retrieve generated session content snippets from cached learning_content.json records.

        Retrieval strategy:
        1) current session first (if provided and valid)
        2) fallback to other sessions in the same goal
        """
        if not user_id or goal_id is None:
            return "Missing user_id/goal_id context for session content retrieval."

        indices = _collect_session_indices(user_id, int(goal_id))
        if not indices:
            return "No learning path/session metadata found for this goal."

        per_doc_chars = min(1000, max(400, max_chars // max(1, top_k)))
        snippets: List[Dict[str, Any]] = []

        # Current session first
        if isinstance(session_index, int) and session_index in indices:
            current_record = store.get_learning_content(user_id, int(goal_id), session_index)
            current_snippet = _extract_doc_snippet(
                user_id=user_id,
                goal_id=int(goal_id),
                session_index=session_index,
                record=current_record or {},
                query=query,
                per_doc_chars=per_doc_chars,
            )
            if current_snippet is not None:
                current_snippet["priority"] = 1
                snippets.append(current_snippet)

        # Goal-wide fallback
        for idx in indices:
            if isinstance(session_index, int) and idx == session_index:
                continue
            record = store.get_learning_content(user_id, int(goal_id), idx)
            item = _extract_doc_snippet(
                user_id=user_id,
                goal_id=int(goal_id),
                session_index=idx,
                record=record or {},
                query=query,
                per_doc_chars=per_doc_chars,
            )
            if item is not None:
                item["priority"] = 2
                snippets.append(item)

        if not snippets:
            return "No generated session content found in cache for this goal."

        # Keep current session first, then rank fallback snippets by overlap score.
        primary = [s for s in snippets if s.get("priority") == 1]
        fallback = [s for s in snippets if s.get("priority") != 1]
        fallback.sort(key=lambda s: int(s.get("score", 0)), reverse=True)
        ranked = (primary + fallback)[:top_k]

        blocks: List[str] = []
        budget = max_chars
        for i, s in enumerate(ranked, start=1):
            block = (
                f"[{i}] {s.get('title')} | Source: {s.get('source')}\n"
                f"{s.get('snippet', '')}"
            )
            if len(block) > budget:
                block = _truncate(block, budget)
            blocks.append(block)
            budget -= len(block) + 2
            if budget <= 120:
                break
        return "\n\n".join(blocks)

    return retrieve_session_learning_content


__all__ = ["RetrieveSessionLearningContentInput", "create_retrieve_session_learning_content_tool"]
