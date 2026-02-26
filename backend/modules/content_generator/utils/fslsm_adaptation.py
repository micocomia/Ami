from __future__ import annotations

import ast
from typing import Any

_FSLSM_STRONG = 0.7
_FSLSM_MODERATE = 0.3


def _as_profile_dict(learner_profile: Any) -> dict:
    if isinstance(learner_profile, str):
        try:
            learner_profile = ast.literal_eval(learner_profile)
        except Exception:
            return {}
    if isinstance(learner_profile, dict):
        return learner_profile
    return {}


def get_fslsm_input(learner_profile: Any) -> float:
    """Extract fslsm_input value from a learner profile dict. Returns 0.0 on missing/error."""
    profile = _as_profile_dict(learner_profile)
    if not profile:
        return 0.0
    try:
        dims = (
            profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        if not isinstance(dims, dict):
            return 0.0
        val = dims.get("fslsm_input", 0.0)
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def get_fslsm_dim(learner_profile: Any, dim_name: str) -> float:
    """Extract a named FSLSM dimension value from a learner profile dict. Returns 0.0 on missing/error."""
    profile = _as_profile_dict(learner_profile)
    if not profile:
        return 0.0
    try:
        dims = (
            profile
            .get("learning_preferences", {})
            .get("fslsm_dimensions", {})
        )
        if not isinstance(dims, dict):
            return 0.0
        val = dims.get(dim_name, 0.0)
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def processing_perception_hints(processing: float, perception: float) -> str:
    """Return per-section hints for the Processing and Perception FSLSM dimensions."""
    parts = []
    if processing <= -_FSLSM_MODERATE:
        parts.append(
            "**Processing Style (Active)**: After each concept, include a "
            "`Try It First` block - a hands-on challenge or trial-and-error simulation "
            "that lets the learner engage directly before the full explanation."
        )
    elif processing >= _FSLSM_MODERATE:
        parts.append(
            "**Processing Style (Reflective)**: After each concept, include a "
            "`Reflection Pause` block - one deep-thinking question that encourages "
            "the learner to connect the concept to prior knowledge before moving on."
        )
    if perception <= -_FSLSM_MODERATE:
        parts.append(
            "**Perception Style (Sensing)**: Present each concept in this order: "
            "(1) a concrete real-world example first, (2) step-by-step facts or procedure, "
            "(3) underlying theory last."
        )
    elif perception >= _FSLSM_MODERATE:
        parts.append(
            "**Perception Style (Intuitive)**: Present each concept in this order: "
            "(1) the abstract principle or theory first, (2) relationships and patterns, "
            "(3) concrete examples last."
        )
    if not parts:
        return ""
    return "\n\n**Learning Style Instructions**:\n" + "\n".join(f"- {p}" for p in parts)


def understanding_hints(understanding: float) -> str:
    """Return document-level structure hint for the Understanding FSLSM dimension."""
    if understanding <= -_FSLSM_MODERATE:
        return (
            "\n\n**Understanding Style (Sequential)**: Structure the document with strict linear "
            "progression. Use explicit 'Building on [previous concept]...' transitions between "
            "sections. Avoid forward references - do not mention concepts before they have been "
            "introduced."
        )
    if understanding >= _FSLSM_MODERATE:
        return (
            "\n\n**Understanding Style (Global)**: Begin the document with a `Big Picture` "
            "section that shows how this session fits into the overall course and learning path. "
            "Use cross-references between sections to highlight connections between ideas."
        )
    return ""


def visual_formatting_hints(fslsm_input: float) -> str:
    """Return formatting instruction hints for visual learners based on fslsm_input score."""
    if fslsm_input <= -_FSLSM_STRONG:
        return (
            "\n\n**Visual Formatting Instructions**: This learner is a strong visual learner. "
            "You MUST include at least one Mermaid diagram (```mermaid ... ```) to illustrate key concepts. "
            "Use markdown tables to present comparisons, steps, or structured data."
        )
    if fslsm_input <= -_FSLSM_MODERATE:
        return (
            "\n\n**Visual Formatting Instructions**: This learner prefers visual content. "
            "Include markdown tables where applicable to present comparisons or structured data. "
            "Use code blocks and structured layouts where applicable."
        )
    return ""


def narrative_allowance(fslsm_input: float) -> int:
    """Narrative inserts (short stories/poems) for verbal learners."""
    if fslsm_input >= _FSLSM_STRONG:
        return 3
    if fslsm_input >= _FSLSM_MODERATE:
        return 1
    return 0
