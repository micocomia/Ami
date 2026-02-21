"""
Goal Assessment Tool for the SkillGapIdentifier agent.

Assesses whether a learning goal is vague (no relevant course content found)
and whether all skills are already mastered (no gaps).
"""

from typing import Any, Dict, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.search_rag import SearchRagManager


class AssessGoalQualityInput(BaseModel):
    """Input schema for goal quality assessment."""

    learning_goal: str = Field(..., description="The learner's goal to assess.")
    skill_gaps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="The identified skill gaps list. Each item should have 'is_gap' bool.",
    )


def create_goal_assessment_tool(search_rag_manager: Optional[SearchRagManager] = None):
    """Factory: returns a LangChain tool bound to the given SearchRagManager."""

    @tool("assess_goal_quality", args_schema=AssessGoalQualityInput)
    def assess_goal_quality(
        learning_goal: str,
        skill_gaps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Assess a learning goal's quality: is it vague? Are all skills already mastered?

        A goal is considered vague when no relevant verified course content is found
        for it (retrieval returns empty). All-mastered is determined by checking
        whether every skill gap has is_gap=false.

        Args:
            learning_goal: The goal string to evaluate.
            skill_gaps: Optional list of skill gap dicts with 'is_gap' fields.

        Returns:
            Dict with is_vague, all_mastered, and suggestion fields.
        """
        # Check vagueness via retrieval
        is_vague = False
        if search_rag_manager is not None and search_rag_manager.verified_content_manager is not None:
            # Goals that explicitly reference a course code are inherently specific
            import re
            course_code_pattern = re.compile(
                r'\b\d+\.\d+\b'           # numeric codes like 6.0001
                r'|[A-Za-z]+\d{3,}'       # alphanumeric codes like DTI5902
                r'|\d+[A-Za-z]+\d*',      # mixed codes like 6EE100
            )
            if not course_code_pattern.search(learning_goal):
                vcm = search_rag_manager.verified_content_manager
                if hasattr(type(vcm), "retrieve_filtered"):
                    docs = vcm.retrieve_filtered(
                        learning_goal,
                        k=3,
                        content_category="Lectures",
                        exclude_file_names=["syllabus.json"],
                        require_lecture=True,
                    )
                else:
                    docs = vcm.retrieve(learning_goal, k=3)
                if not docs:
                    is_vague = True
        # Without verified content, we cannot assess vagueness via retrieval
        # so we leave is_vague=False and let the LLM decide

        # Check all-mastered
        all_mastered = False
        if skill_gaps is not None and len(skill_gaps) > 0:
            all_mastered = all(not gap.get("is_gap", True) for gap in skill_gaps)

        # Build suggestion
        suggestion = ""
        if is_vague:
            suggestion = (
                "Your goal may be too vague or does not match available course content. "
                "Consider making it more specific (e.g., include a topic area or skill)."
            )
        elif all_mastered:
            suggestion = (
                "You already master all required skills for this goal. "
                "Consider setting a more advanced goal or exploring a different topic."
            )

        return {
            "is_vague": is_vague,
            "all_mastered": all_mastered,
            "suggestion": suggestion,
        }

    return assess_goal_quality
