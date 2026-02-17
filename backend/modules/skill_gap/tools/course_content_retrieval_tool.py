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
    content_category: Optional[str] = Field(
        default=None,
        description="Filter by content category (e.g., 'Syllabus', 'Lectures'). None returns all.",
    )
    lecture_number: Optional[int] = Field(
        default=None,
        description="Filter by specific lecture number. Only applies when content_category='Lectures'.",
    )
    k: int = Field(default=5, description="Number of results to retrieve.")


def create_course_content_retrieval_tool(search_rag_manager: Optional[SearchRagManager] = None):
    """Factory: returns a LangChain tool bound to the given SearchRagManager."""

    @tool("retrieve_course_content", args_schema=RetrieveCourseContentInput)
    def retrieve_course_content(
        query: str,
        content_category: Optional[str] = None,
        lecture_number: Optional[int] = None,
        k: int = 5,
    ) -> str:
        """Retrieve verified course content (syllabus, lectures) relevant to a query.

        Use this to ground skill requirements in actual course material.
        Query the syllabus first for broad coverage, then specific lectures if needed.

        Args:
            query: The search query.
            content_category: Optional filter — 'Syllabus' or 'Lectures'.
            lecture_number: Optional lecture number filter.
            k: Number of results.

        Returns:
            Formatted string of matching documents, or a message if none found.
        """
        if search_rag_manager is None or search_rag_manager.verified_content_manager is None:
            return "No verified course content available. Proceed using your own knowledge."

        vcm = search_rag_manager.verified_content_manager
        docs = vcm.retrieve(query, k=k * 3)  # over-fetch for filtering

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

        return format_docs(docs)

    return retrieve_course_content
