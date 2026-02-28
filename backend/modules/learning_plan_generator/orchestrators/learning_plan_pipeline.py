import logging
from typing import Any, Dict, Mapping, Optional, Tuple

from modules.learning_plan_generator.agents.learning_path_scheduler import LearningPathScheduler
from modules.learning_plan_generator.tools.learner_simulation_tool import create_simulate_feedback_tool


JSONDict = Dict[str, Any]
logger = logging.getLogger(__name__)


def schedule_learning_path_agentic(
    llm: Any,
    learner_profile: Mapping[str, Any],
    session_count: int = 0,
    max_refinements: int = 1,
    goal_context: Optional[Mapping[str, Any]] = None,
) -> Tuple[JSONDict, Dict[str, Any]]:
    """Agentic learning path generation with auto-refinement.

    Flow:
    1. Generate initial plan
    2. Evaluate plan quality via learner simulator tool (gpt-4o-mini)
    3. Read is_acceptable, issues, improvement_directives from simulation feedback
    4. If quality insufficient, feed improvement_directives into reflexion()
    5. At most ``max_refinements`` reflexion passes (default 1 → two LLM calls total)
    6. Return final plan + evaluation metadata
    """
    sim_tool = create_simulate_feedback_tool(llm, use_ground_truth=False)

    plan = None
    simulation_feedback: Any = {}
    quality: Dict[str, Any] = {"pass": False, "issues": [], "feedback_summary": {}}
    evaluator_feedback: str = ""
    attempt = 0

    scheduler = LearningPathScheduler(llm)

    for attempt in range(1 + max_refinements):
        if attempt == 0:
            plan = scheduler.schedule_session({
                "learner_profile": learner_profile,
                "session_count": session_count,
                "goal_context": goal_context,
            })
        else:
            plan = scheduler.reflexion({
                "learning_path": plan.get("learning_path", []),
                "feedback": {
                    "learner_profile": learner_profile,
                    "simulation_feedback": simulation_feedback,
                },
                "evaluator_feedback": evaluator_feedback,
                "goal_context": goal_context,
            })

        # Evaluate via learner simulation (gpt-4o-mini, fast path)
        learning_path_list = plan.get("learning_path", [])
        profile_dict = dict(learner_profile) if isinstance(learner_profile, Mapping) else learner_profile

        simulation_feedback = sim_tool.invoke({
            "learning_path": learning_path_list,
            "learner_profile": profile_dict,
        })

        if not isinstance(simulation_feedback, dict):
            simulation_feedback = {}

        quality = {
            "pass": simulation_feedback.get("is_acceptable", True),
            "issues": simulation_feedback.get("issues", []),
            "feedback_summary": simulation_feedback.get("feedback", {}),
        }
        evaluator_feedback = simulation_feedback.get("improvement_directives", "")

        if quality["pass"]:
            break
        else:
            logger.info(
                "Plan quality check failed (attempt %d/%d). Issues: %s",
                attempt + 1,
                1 + max_refinements,
                quality["issues"],
            )

    metadata = {
        "refinement_iterations": attempt + 1,
        "evaluation": quality,
        "last_simulation_feedback": simulation_feedback,
    }

    return plan, metadata
