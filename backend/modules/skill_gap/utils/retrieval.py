from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.documents import Document

from base.search_rag import SearchRagManager


def _retrieve_context_for_goal(
    goal_context: Dict[str, Any],
    search_rag_manager: Optional[SearchRagManager],
) -> List[Document]:
    """Deterministically retrieve course content using parsed goal context."""
    if search_rag_manager is None or search_rag_manager.verified_content_manager is None:
        return []

    vcm = search_rag_manager.verified_content_manager
    course_code = goal_context.get("course_code")
    lecture_number = goal_context.get("lecture_number")
    content_category = goal_context.get("content_category")
    page_number = goal_context.get("page_number")

    query_parts = [p for p in [
        f"course {course_code}" if course_code else None,
        f"lecture {lecture_number}" if lecture_number else None,
        "content",
    ] if p]
    query = " ".join(query_parts)

    effective_category = content_category or ("Lectures" if lecture_number else None)
    require_lecture = bool(effective_category == "Lectures") if effective_category else bool(lecture_number)
    exclude = ["syllabus.json"] if require_lecture else None

    if hasattr(type(vcm), "retrieve_filtered"):
        return vcm.retrieve_filtered(
            query=query,
            k=8,
            course_code=course_code,
            content_category=effective_category,
            lecture_number=lecture_number,
            page_number=page_number,
            exclude_file_names=exclude,
            require_lecture=require_lecture,
        )
    return vcm.retrieve(query, k=8)
