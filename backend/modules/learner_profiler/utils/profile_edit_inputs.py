"""Input normalization helpers for learner profile edit flows."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Mapping, Optional

_DIM_CANONICAL_KEYS = {
    "processing": "fslsm_processing",
    "fslsm_processing": "fslsm_processing",
    "perception": "fslsm_perception",
    "fslsm_perception": "fslsm_perception",
    "input": "fslsm_input",
    "fslsm_input": "fslsm_input",
    "understanding": "fslsm_understanding",
    "fslsm_understanding": "fslsm_understanding",
}

_FSLSM_KEYS = (
    "fslsm_processing",
    "fslsm_perception",
    "fslsm_input",
    "fslsm_understanding",
)


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Normalize whitespace without flattening line breaks completely.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.split("\n"))
    return text.strip()


def clamp_fslsm_value(value: Any, *, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = float(default)
    numeric = max(-1.0, min(1.0, numeric))
    return round(numeric, 6)


def normalize_fslsm_slider_values(
    slider_values: Any,
    *,
    fallback_dims: Optional[Mapping[str, Any]] = None,
) -> Dict[str, float]:
    """Normalize mixed slider key shapes into canonical fslsm_* dimensions."""
    fallback_dims = fallback_dims or {}
    normalized: Dict[str, float] = {}
    source = slider_values if isinstance(slider_values, Mapping) else {}
    for key in _FSLSM_KEYS:
        fallback_val = fallback_dims.get(key, 0.0)
        normalized[key] = clamp_fslsm_value(fallback_val, default=0.0)
    for raw_key, raw_val in source.items():
        canonical = _DIM_CANONICAL_KEYS.get(str(raw_key).strip().lower())
        if canonical is None:
            continue
        normalized[canonical] = clamp_fslsm_value(raw_val, default=normalized.get(canonical, 0.0))
    return normalized


def extract_slider_override_dims(
    learner_interactions: Any,
    *,
    fallback_dims: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, float]]:
    """Return normalized slider override dims when the payload requests explicit FSLSM override."""
    if not isinstance(learner_interactions, Mapping):
        return None
    mode = str(learner_interactions.get("update_mode", "")).strip().lower()
    if mode != "fslsm_slider_override":
        return None
    raw_slider_values = learner_interactions.get("slider_values", {})
    if not isinstance(raw_slider_values, Mapping):
        return None
    return normalize_fslsm_slider_values(raw_slider_values, fallback_dims=fallback_dims)


def compose_learner_information_update_inputs(
    *,
    current_learner_information: Any,
    edited_learner_information: Any,
    resume_text: Any,
    edited_max_chars: int = 8000,
    resume_max_chars: int = 20000,
) -> Dict[str, str]:
    """Compose text-primary learner-information inputs with compaction and truncation."""
    current_text = _compact_text(current_learner_information)
    edited_text = _compact_text(edited_learner_information)
    resume_compact = _compact_text(resume_text)

    if edited_max_chars > 0:
        edited_text = edited_text[:edited_max_chars]
    if resume_max_chars > 0:
        resume_compact = resume_compact[:resume_max_chars]

    primary_text = edited_text if edited_text else current_text

    return {
        "current_learner_information": current_text,
        "edited_learner_information": edited_text,
        "resume_text": resume_compact,
        "primary_learner_information": primary_text,
    }


def preserve_profile_sections_for_info_only_update(
    original_profile: Mapping[str, Any],
    candidate_profile: Mapping[str, Any],
) -> Dict[str, Any]:
    """Allow only learner_information to change for info-only updates."""
    original = copy.deepcopy(dict(original_profile or {}))
    candidate = copy.deepcopy(dict(candidate_profile or {}))
    result = copy.deepcopy(original)
    result["learner_information"] = str(candidate.get("learner_information", original.get("learner_information", "")))
    for key in ("learning_goal", "goal_display_name", "cognitive_status", "learning_preferences", "behavioral_patterns"):
        if key in original:
            result[key] = copy.deepcopy(original[key])
    return result
