from typing import Any, Dict, Mapping, Optional, Tuple
import json

from modules.learning_plan_generator.agents.learning_path_scheduler import LearningPathScheduler
from modules.tools.learner_simulation_tool import create_simulate_feedback_tool


JSONDict = Dict[str, Any]

_NEGATIVE_KEYWORDS = [
    "needs improvement", "poor", "weak", "lacking", "insufficient",
    "missing", "not aligned", "not personalized", "disengaging",
    "too easy", "too difficult", "repetitive", "monotonous",
    "no progression", "confusing", "unclear",
]


def _evaluate_plan_quality(simulation_feedback: Any) -> Dict[str, Any]:
    """Deterministic quality gate on learner simulation feedback.

    Parses the simulation feedback (progression, engagement, personalization)
    and checks for negative signals (keyword-based heuristic + suggestion count).
    Returns: {"pass": bool, "issues": [...], "feedback_summary": {...}}
    """
    if not isinstance(simulation_feedback, dict):
        return {"pass": True, "issues": [], "feedback_summary": {}}

    feedback_text = json.dumps(simulation_feedback, default=str).lower()
    issues = []

    for keyword in _NEGATIVE_KEYWORDS:
        if keyword in feedback_text:
            issues.append(keyword)

    # Check suggestion count — more than 3 distinct suggestions is a concern
    suggestions = simulation_feedback.get("suggestions", [])
    if isinstance(suggestions, list) and len(suggestions) > 3:
        issues.append(f"high_suggestion_count ({len(suggestions)})")
    elif isinstance(suggestions, dict):
        total = sum(
            len(v) if isinstance(v, list) else (1 if v else 0)
            for v in suggestions.values()
        )
        if total > 3:
            issues.append(f"high_suggestion_count ({total})")

    # Extract from nested "feedback" dict (LearnerFeedback schema)
    feedback_detail = simulation_feedback.get("feedback", {})
    if not isinstance(feedback_detail, dict):
        feedback_detail = {}
    feedback_summary = {}
    for key in ("progression", "engagement", "personalization"):
        val = feedback_detail.get(key)
        if val is not None:
            feedback_summary[key] = val

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "feedback_summary": feedback_summary,
    }


def schedule_learning_path_agentic(
    llm: Any,
    learner_profile: Mapping[str, Any],
    session_count: int = 0,
    max_refinements: int = 2,
    goal_context: Optional[Mapping[str, Any]] = None,
) -> Tuple[JSONDict, Dict[str, Any]]:
    """Agentic learning path generation with auto-refinement.

    Flow:
    1. Generate initial plan
    2. Evaluate plan quality via learner simulator tool (gpt-4o-mini)
    3. Run deterministic quality gate on simulation feedback
    4. If quality insufficient, feed simulation feedback into reflexion()
    5. Max ``max_refinements`` refinement iterations (latency guardrail)
    6. Return final plan + evaluation metadata
    """
    sim_tool = create_simulate_feedback_tool(llm, use_ground_truth=False)

    plan = None
    simulation_feedback: Any = {}
    quality: Dict[str, Any] = {"pass": False, "issues": [], "feedback_summary": {}}
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
                "goal_context": goal_context,
            })

        # Evaluate via learner simulation (gpt-4o-mini, fast path)
        learning_path_list = plan.get("learning_path", [])
        profile_dict = dict(learner_profile) if isinstance(learner_profile, Mapping) else learner_profile

        simulation_feedback = sim_tool.invoke({
            "learning_path": learning_path_list,
            "learner_profile": profile_dict,
        })

        quality = _evaluate_plan_quality(simulation_feedback)
        if quality["pass"]:
            break

    metadata = {
        "refinement_iterations": attempt + 1,
        "evaluation": quality,
        "last_simulation_feedback": simulation_feedback,
    }

    return plan, metadata
