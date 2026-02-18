"""
Course Content Retrieval Tool for skill gap agents.

Wraps VerifiedContentManager.retrieve() with in-memory metadata filtering
so agents can query syllabus, lectures, or any verified course content.
"""

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager, format_docs


class RetrieveCourseContentInput(BaseModel):
    """Input schema for course content retrieval."""

    query: str = Field(..., description="The search query to retrieve relevant course content.")
    course_code: Optional[str] = Field(
        default=None,
        description="Filter by course code (e.g., '6.0001', '11.437'). None returns all courses.",
    )
    course_name: Optional[str] = Field(
        default=None,
        description="Filter by course name (substring match, case-insensitive, e.g., 'intro cs'). None returns all courses.",
    )
    content_category: Optional[str] = Field(
        default=None,
        description="Filter by content category (e.g., 'Syllabus', 'Lectures'). None returns all.",
    )
    lecture_number: Optional[int] = Field(
        default=None,
        description="Filter by specific lecture number. Only applies when content_category='Lectures'.",
    )
    k: int = Field(default=8, description="Number of results to retrieve.")


def create_course_content_retrieval_tool(
    search_rag_manager: Optional[SearchRagManager] = None,
    retrieved_docs_sink: Optional[List[Dict[str, Any]]] = None,
):
    """Factory: returns a LangChain tool bound to the given SearchRagManager.

    Args:
        search_rag_manager: Optional RAG manager for verified content retrieval.
        retrieved_docs_sink: Optional list that will be mutated in-place to
            collect metadata dicts of every document retrieved by the tool.
    """

    @tool("retrieve_course_content", args_schema=RetrieveCourseContentInput)
    def retrieve_course_content(
        query: str,
        course_code: Optional[str] = None,
        course_name: Optional[str] = None,
        content_category: Optional[str] = None,
        lecture_number: Optional[int] = None,
        k: int = 8,
    ) -> str:
        """Retrieve verified course content (syllabus, lectures) relevant to a query.

        Use this to ground skill requirements in actual course material.
        Retrieve lectures for topic-level content; use syllabus only if you need broad course structure.

        Args:
            query: The search query.
            course_code: Optional course code filter (e.g., '6.0001').
            course_name: Optional course name substring filter (e.g., 'intro cs').
            content_category: Optional filter — 'Syllabus' or 'Lectures'.
            lecture_number: Optional lecture number filter.
            k: Number of results.

        Returns:
            Formatted string of matching documents, or a message if none found.
        """
        if search_rag_manager is None or search_rag_manager.verified_content_manager is None:
            return "No verified course content available. Proceed using your own knowledge."

        vcm = search_rag_manager.verified_content_manager
        docs = vcm.retrieve(query, k=k * 4)  # over-fetch for filtering

        if course_code:
            docs = [
                d for d in docs
                if d.metadata.get("course_code", "").lower() == course_code.lower()
            ]

        if course_name:
            docs = [
                d for d in docs
                if course_name.lower() in d.metadata.get("course_name", "").lower()
            ]

        if content_category:
            docs = [
                d for d in docs
                if d.metadata.get("content_category", "").lower() == content_category.lower()
            ]

        if lecture_number is not None:
            docs = [
                d for d in docs
                if d.metadata.get("lecture_number") == lecture_number
            ]

        docs = docs[:k]

        if not docs:
            return f"No results found for query '{query}' with the given filters. Try a broader query or proceed with your own knowledge."

        # Capture metadata for downstream citation display
        if retrieved_docs_sink is not None:
            for d in docs:
                retrieved_docs_sink.append(dict(d.metadata) if d.metadata else {})

        return format_docs(docs)

    return retrieve_course_content
