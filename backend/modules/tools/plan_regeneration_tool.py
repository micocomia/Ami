"""
Plan Regeneration Decision Tool.

Deterministic logic to decide whether to keep, adjust, or regenerate
a learning path based on detected preference/mastery changes.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from base.llm_factory import LLMFactory


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class RegenerationDecision(BaseModel):
    """The output of the plan regeneration decision logic."""

    action: Literal["keep", "adjust_future", "regenerate"] = Field(
        ..., description="The adaptation strategy."
    )
    reason: str = Field(
        ..., description="Human-readable explanation of why this decision was made."
    )
    affected_sessions: List[int] = Field(
        default_factory=list,
        description="Indices of sessions affected by the decision.",
    )


# ---------------------------------------------------------------------------
# FSLSM delta thresholds
# ---------------------------------------------------------------------------

_KEEP_THRESHOLD = 0.3       # abs delta < 0.3 on ALL dims → keep
_ADJUST_THRESHOLD = 0.5     # abs delta in [0.3, 0.5) → adjust future
# abs delta >= 0.5 on any dim → regenerate

_DIM_LABELS = {
    "fslsm_processing": "processing (active vs. reflective)",
    "fslsm_perception": "perception (sensing vs. intuitive)",
    "fslsm_input": "input (visual vs. verbal)",
    "fslsm_understanding": "understanding (sequential vs. global)",
}


# ---------------------------------------------------------------------------
# Core deterministic logic
# ---------------------------------------------------------------------------

def compute_fslsm_deltas(
    old_prefs: Dict[str, Any],
    new_prefs: Dict[str, Any],
) -> Dict[str, float]:
    """Compute absolute deltas between old and new FSLSM dimensions.

    Args:
        old_prefs: Previous learner profile's fslsm_dimensions dict.
        new_prefs: Updated learner profile's fslsm_dimensions dict.

    Returns:
        Dict mapping dimension name to absolute delta value.
    """
    dims = [
        "fslsm_processing",
        "fslsm_perception",
        "fslsm_input",
        "fslsm_understanding",
    ]
    deltas = {}
    for dim in dims:
        old_val = float(old_prefs.get(dim, 0.0))
        new_val = float(new_prefs.get(dim, 0.0))
        deltas[dim] = abs(old_val - new_val)
    return deltas


def count_mastery_failures(
    mastery_results: List[Dict[str, Any]],
) -> int:
    """Count sessions where mastery was not achieved."""
    return sum(
        1 for r in mastery_results
        if not r.get("is_mastered", True)
    )


def decide_regeneration(
    current_plan: Dict[str, Any],
    old_preferences: Dict[str, Any],
    new_preferences: Dict[str, Any],
    mastery_results: Optional[List[Dict[str, Any]]] = None,
) -> RegenerationDecision:
    """Deterministic decision on whether to keep, adjust, or regenerate.

    Decision logic:
    - KEEP:  abs(old - new) < 0.3 on ALL dims AND all mastery on track
    - ADJUST_FUTURE: any dim delta in [0.3, 0.5) OR single mastery failure
    - REGENERATE: any dim delta >= 0.5 OR multiple mastery failures

    Args:
        current_plan: The existing learning path dict.
        old_preferences: Previous FSLSM dimensions dict.
        new_preferences: Updated FSLSM dimensions dict.
        mastery_results: List of {session_id, score, is_mastered, threshold}.

    Returns:
        RegenerationDecision with action, reason, and affected session indices.
    """
    mastery_results = mastery_results or []
    deltas = compute_fslsm_deltas(old_preferences, new_preferences)
    failures = count_mastery_failures(mastery_results)

    max_delta = max(deltas.values()) if deltas else 0.0
    max_delta_dim = max(deltas, key=deltas.get) if deltas else ""

    sessions = current_plan.get("learning_path", [])
    future_indices = [
        i for i, s in enumerate(sessions)
        if not s.get("if_learned", False)
    ]

    dim_label = _DIM_LABELS.get(max_delta_dim, max_delta_dim)

    # REGENERATE conditions
    if max_delta >= _ADJUST_THRESHOLD:
        return RegenerationDecision(
            action="regenerate",
            reason=f"Major shift in {dim_label} preference detected. Regenerating future sessions.",
            affected_sessions=future_indices,
        )

    if failures >= 2:
        failed_indices = [
            i for i, r in enumerate(mastery_results)
            if not r.get("is_mastered", True)
        ]
        return RegenerationDecision(
            action="regenerate",
            reason=f"Mastery not achieved in {failures} sessions. Regenerating future sessions with reinforcement.",
            affected_sessions=failed_indices + future_indices,
        )

    # ADJUST_FUTURE conditions
    if max_delta >= _KEEP_THRESHOLD:
        return RegenerationDecision(
            action="adjust_future",
            reason=f"Shift in {dim_label} preference detected. Adjusting future sessions.",
            affected_sessions=future_indices,
        )

    if failures == 1:
        failed_idx = next(
            (i for i, r in enumerate(mastery_results) if not r.get("is_mastered", True)),
            None,
        )
        affected = [failed_idx] + future_indices if failed_idx is not None else future_indices
        return RegenerationDecision(
            action="adjust_future",
            reason="Mastery not achieved in a session. Adjusting future sessions with reinforcement.",
            affected_sessions=affected,
        )

    # KEEP
    return RegenerationDecision(
        action="keep",
        reason="No significant preference changes or mastery issues detected.",
        affected_sessions=[],
    )


def generate_reason_with_llm(
    decision: RegenerationDecision,
    deltas: Dict[str, float],
    mastery_results: List[Dict[str, Any]],
) -> str:
    """Use gpt-4o-mini to generate a human-readable reason string.

    This is optional — the deterministic reason from decide_regeneration()
    is already informative. This adds a more natural-language explanation.
    """
    try:
        fast_llm = LLMFactory.create(
            model="gpt-4o-mini",
            model_provider="openai",
            temperature=0,
        )
        prompt = (
            f"Summarize this learning path adaptation decision in 1-2 sentences "
            f"for a learner:\n"
            f"Action: {decision.action}\n"
            f"FSLSM dimension deltas: {deltas}\n"
            f"Mastery results: {mastery_results}\n"
            f"Technical reason: {decision.reason}\n\n"
            f"Write a friendly, clear explanation:"
        )
        response = fast_llm.invoke(prompt)
        if hasattr(response, "content"):
            return response.content
        return str(response)
    except Exception:
        return decision.reason
