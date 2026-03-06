from __future__ import annotations

import ast
import json
from typing import Any

_FSLSM_STRONG = 0.7
_FSLSM_MODERATE = 0.3


def _as_mapping(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except Exception:
            return {}
    if isinstance(value, dict):
        return value
    return {}


def get_fslsm_input(learner_profile: Any) -> float:
    """Extract fslsm_input value from a learner profile dict. Returns 0.0 on missing/error."""
    profile = _as_mapping(learner_profile)
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
    profile = _as_mapping(learner_profile)
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


def build_session_adaptation_contract(learning_session: Any, learner_profile: Any) -> dict[str, Any]:
    """Derive a richer backend-only session adaptation contract.

    Scheduled session fields are the primary source of truth. Raw FSLSM scores only
    recover intensity when the scheduled session does not encode it directly.
    """
    session = _as_mapping(learning_session)
    processing_score = get_fslsm_dim(learner_profile, "fslsm_processing")
    perception_score = get_fslsm_dim(learner_profile, "fslsm_perception")

    has_checkpoint = bool(session.get("has_checkpoint_challenges", False))
    thinking_minutes = int(session.get("thinking_time_buffer_minutes") or 0)
    sequence_hint = str(session.get("session_sequence_hint") or "").strip().lower()

    processing_mode = "balanced"
    processing_intensity = "none"
    checkpoint_frequency = "none"
    reflection_level = "none"

    if has_checkpoint:
        processing_mode = "active"
        processing_intensity = "strong" if processing_score <= -_FSLSM_STRONG else "mild"
        checkpoint_frequency = "multiple" if processing_intensity == "strong" else "single"
    elif thinking_minutes > 0:
        processing_mode = "reflective"
        processing_intensity = "strong" if (thinking_minutes >= 10 or processing_score >= _FSLSM_STRONG) else "mild"
        reflection_level = "extended" if thinking_minutes >= 10 else "brief"

    perception_mode = "balanced"
    perception_intensity = "none"
    conceptual_leap_allowance = "normal"
    section_order = ["concept", "example", "application"]

    if sequence_hint == "application-first":
        perception_mode = "application_first"
        perception_intensity = "strong" if perception_score <= -_FSLSM_STRONG else "mild"
        conceptual_leap_allowance = "low"
        section_order = ["application", "example", "theory"]
    elif sequence_hint == "theory-first":
        perception_mode = "theory_first"
        perception_intensity = "strong" if perception_score >= _FSLSM_STRONG else "mild"
        conceptual_leap_allowance = "high" if perception_intensity == "strong" else "normal"
        section_order = ["theory", "pattern", "example"]

    input_score = get_fslsm_dim(learner_profile, "fslsm_input")
    understanding_score = get_fslsm_dim(learner_profile, "fslsm_understanding")

    if input_score <= -_FSLSM_STRONG:
        input_mode = "strong_visual"
    elif input_score <= -_FSLSM_MODERATE:
        input_mode = "mild_visual"
    elif input_score >= _FSLSM_STRONG:
        input_mode = "strong_verbal"
    elif input_score >= _FSLSM_MODERATE:
        input_mode = "mild_verbal"
    else:
        input_mode = "balanced"

    if understanding_score <= -_FSLSM_STRONG:
        understanding_mode, understanding_intensity = "sequential", "strong"
    elif understanding_score <= -_FSLSM_MODERATE:
        understanding_mode, understanding_intensity = "sequential", "mild"
    elif understanding_score >= _FSLSM_STRONG:
        understanding_mode, understanding_intensity = "global", "strong"
    elif understanding_score >= _FSLSM_MODERATE:
        understanding_mode, understanding_intensity = "global", "mild"
    else:
        understanding_mode, understanding_intensity = "balanced", "none"

    return {
        "processing": {
            "mode": processing_mode,
            "intensity": processing_intensity,
            "checkpoint_frequency": checkpoint_frequency,
            "reflection_level": reflection_level,
        },
        "perception": {
            "mode": perception_mode,
            "intensity": perception_intensity,
            "conceptual_leap_allowance": conceptual_leap_allowance,
            "section_order": section_order,
        },
        "input": {
            "mode": input_mode,
            "has_visual_formatting": input_score <= -_FSLSM_MODERATE,
            "audio_mode": (
                "podcast" if input_score >= _FSLSM_STRONG
                else "narration" if input_score >= _FSLSM_MODERATE
                else "none"
            ),
        },
        "understanding": {
            "mode": understanding_mode,
            "intensity": understanding_intensity,
        },
    }


def format_session_adaptation_contract(contract: Any) -> str:
    """Return a stable prompt-friendly JSON rendering of the internal contract."""
    if isinstance(contract, str):
        return contract.strip()
    if isinstance(contract, dict):
        try:
            return json.dumps(contract, indent=2, sort_keys=True)
        except Exception:
            return str(contract)
    return ""


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
