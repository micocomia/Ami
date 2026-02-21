"""
Learner Simulation Tool for LearningPathScheduler.

This module provides a LangChain-compatible tool that wraps the LearningPlanFeedbackSimulator,
enabling the LearningPathScheduler to autonomously evaluate and refine learning paths.

The tool uses a faster model (GPT-4o-mini) for simulation to speed up the process.
"""

from typing import Any, Dict, List, Optional, Union
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from base.llm_factory import LLMFactory
from modules.learner_simulator import (
    LearningPlanFeedbackSimulator,
    create_ground_truth_profile_with_llm,
)


# Default fast model for simulation
SIMULATION_MODEL = "gpt-4o-mini"
SIMULATION_PROVIDER = "openai"


class SimulateFeedbackInput(BaseModel):
    """Input schema for the learner feedback simulation tool."""

    learning_path: List[Dict[str, Any]] = Field(
        ...,
        description="The learning path to evaluate. A list of session objects with id, title, abstract, etc."
    )
    learner_profile: Dict[str, Any] = Field(
        ...,
        description="The learner's profile containing learning goals, skill gaps, preferences, etc."
    )
    ground_truth_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional pre-computed ground truth profile. If provided, skips ground truth generation for faster simulation."
    )


def create_simulate_feedback_tool(
    llm: Any,
    simulation_model: Optional[str] = None,
    simulation_provider: Optional[str] = None,
    use_ground_truth: bool = True
):
    """
    Factory function to create a feedback simulation tool.

    Args:
        llm: The main language model (used for ground truth creation if needed).
        simulation_model: Model to use for simulation (default: gpt-4o-mini for speed).
        simulation_provider: Provider for simulation model (default: openai).
        use_ground_truth: If True, uses enriched ground-truth profile for simulation.

    Returns:
        A LangChain tool that can be used by agents.
    """
    # Use faster model for simulation
    sim_model = simulation_model or SIMULATION_MODEL
    sim_provider = simulation_provider or SIMULATION_PROVIDER

    # Create a fast LLM for simulation
    fast_llm = LLMFactory.create(
        model=sim_model,
        model_provider=sim_provider,
        temperature=0
    )

    simulator = LearningPlanFeedbackSimulator(fast_llm)

    @tool("simulate_learner_feedback", args_schema=SimulateFeedbackInput)
    def simulate_learner_feedback(
        learning_path: List[Dict[str, Any]],
        learner_profile: Dict[str, Any],
        ground_truth_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Simulate how a learner would respond to a proposed learning path.

        This tool simulates realistic feedback based on the learner's characteristics,
        including their patience level, engagement style, and learning preferences.

        For faster simulation, pass a pre-computed ground_truth_profile.
        If not provided and use_ground_truth is True, one will be generated.

        Args:
            learning_path: The proposed learning path to evaluate.
            learner_profile: The learner's profile with goals, skills, and preferences.
            ground_truth_profile: Optional pre-computed ground truth for faster simulation.

        Returns:
            A dictionary containing:
            - feedback: Qualitative assessment of progression, engagement, personalization
            - suggestions: Recommended improvements for each dimension
        """
        if use_ground_truth:
            # Use provided ground truth or create one
            if ground_truth_profile:
                simulation_profile = ground_truth_profile.get("ground_truth_profile", ground_truth_profile)
            else:
                # Create ground truth from learner profile (slower path)
                ground_truth_result = create_ground_truth_profile_with_llm(
                    llm, learner_profile
                )
                simulation_profile = ground_truth_result.get("ground_truth_profile", ground_truth_result)

            payload = {
                "learner_profile": simulation_profile,
                "learning_path": learning_path,
            }

            feedback_result = simulator.feedback_path(payload)

            # Add metadata about simulation
            if isinstance(feedback_result, dict):
                feedback_result["simulation_metadata"] = {
                    "used_ground_truth": True,
                    "ground_truth_provided": ground_truth_profile is not None,
                    "simulation_model": sim_model,
                }

            return feedback_result
        else:
            # Use learner profile directly (fastest path, less personalized)
            payload = {
                "learner_profile": learner_profile,
                "learning_path": learning_path,
            }
            feedback_result = simulator.feedback_path(payload)

            if isinstance(feedback_result, dict):
                feedback_result["simulation_metadata"] = {
                    "used_ground_truth": False,
                    "simulation_model": sim_model,
                }

            return feedback_result

    return simulate_learner_feedback
