"""
Goal Refinement Tool.

Wraps the existing LearningGoalRefiner agent so the orchestrator
can auto-refine vague goals without user intervention.
"""

from typing import Any, Dict, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from modules.skill_gap.agents.learning_goal_refiner import LearningGoalRefiner


class RefineGoalInput(BaseModel):
    """Input schema for goal refinement."""

    learning_goal: str = Field(..., description="The learning goal to refine.")
    learner_information: str = Field(
        default="",
        description="Learner background info (resume, persona, etc.) to personalize the refinement.",
    )
    course_context: str = Field(
        default="",
        description="Retrieved course content to ground the refinement in actual material.",
    )


def create_goal_refinement_tool(llm: Any):
    """Factory: returns a LangChain tool that wraps LearningGoalRefiner."""

    @tool("refine_learning_goal", args_schema=RefineGoalInput)
    def refine_learning_goal(
        learning_goal: str,
        learner_information: str = "",
        course_context: str = "",
    ) -> Dict[str, Any]:
        """Refine a vague learning goal into a clearer, more actionable objective.

        Uses the learner's background and any available course context to produce
        a specific, skill-mappable goal while preserving the original intent.

        Args:
            learning_goal: The original goal to refine.
            learner_information: Background info about the learner.
            course_context: Retrieved course content for grounding.

        Returns:
            Dict with refined_goal, was_refined, and refinement_reason.
        """
        # Combine learner info with course context for richer refinement
        combined_info = learner_information
        if course_context:
            combined_info += f"\n\nRelevant course content:\n{course_context}"

        refiner = LearningGoalRefiner(llm)
        result = refiner.refine_goal({
            "learning_goal": learning_goal,
            "learner_information": combined_info,
        })

        refined_goal = result.get("refined_goal", learning_goal)
        was_refined = refined_goal.strip().lower() != learning_goal.strip().lower()

        return {
            "refined_goal": refined_goal,
            "was_refined": was_refined,
            "refinement_reason": "Goal was refined for clarity and specificity." if was_refined else "Goal was already specific enough.",
        }

    return refine_learning_goal
