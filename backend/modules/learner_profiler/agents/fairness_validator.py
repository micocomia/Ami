from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, TypeAlias

from pydantic import BaseModel, Field
from base import BaseAgent
from ..prompts.fairness_validator import fairness_validator_system_prompt, fairness_validator_task_prompt
from ..schemas import ProfileFairnessResult, FairnessFlag, FSLSMDeviationFlag, FairnessSeverity

logger = logging.getLogger(__name__)

JSONDict: TypeAlias = Dict[str, Any]

# Known persona baselines (mirrored from frontend/utils/personas.py)
_PERSONA_BASELINES: Dict[str, Dict[str, float]] = {
    "Hands-on Explorer": {
        "fslsm_processing": -0.7,
        "fslsm_perception": -0.5,
        "fslsm_input": -0.5,
        "fslsm_understanding": -0.5,
    },
    "Reflective Reader": {
        "fslsm_processing": 0.7,
        "fslsm_perception": 0.5,
        "fslsm_input": 0.7,
        "fslsm_understanding": 0.5,
    },
    "Visual Learner": {
        "fslsm_processing": -0.2,
        "fslsm_perception": -0.3,
        "fslsm_input": -0.8,
        "fslsm_understanding": -0.3,
    },
    "Conceptual Thinker": {
        "fslsm_processing": 0.5,
        "fslsm_perception": 0.7,
        "fslsm_input": 0.0,
        "fslsm_understanding": 0.7,
    },
    "Balanced Learner": {
        "fslsm_processing": 0.0,
        "fslsm_perception": 0.0,
        "fslsm_input": 0.0,
        "fslsm_understanding": 0.0,
    },
}

# Stereotype phrases to detect (case-insensitive)
_STEREOTYPE_PHRASES = [
    "as an engineer",
    "typical for",
    "as expected from",
    "naturally inclined",
    "inherently",
    "as a woman",
    "as a man",
    "given their age",
    "from that background",
    "people from",
    "for someone like you",
    "your kind of",
    "not typical for",
    "despite being",
    "for your level",
    "as a young person",
    "as an older person",
    "culturally speaking",
]

# Threshold for flagging FSLSM deviation from persona baseline
_FSLSM_DEVIATION_THRESHOLD = 0.4

# Dimension display names
_DIMENSION_NAMES = {
    "fslsm_processing": "Processing (Active-Reflective)",
    "fslsm_perception": "Perception (Sensing-Intuitive)",
    "fslsm_input": "Input (Visual-Verbal)",
    "fslsm_understanding": "Understanding (Sequential-Global)",
}


class FairnessValidationPayload(BaseModel):
    """Validated input for the fairness validator."""
    learner_information: str = Field(...)
    learner_profile: dict = Field(...)
    persona_name: str = Field(default="")


class FairnessValidator(BaseAgent):
    """Post-processing agent that validates learner profiles for fairness."""

    name: str = "FairnessValidator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=fairness_validator_system_prompt,
            jsonalize_output=True,
        )

    def validate_profile(self, input_dict: dict) -> JSONDict:
        """Run fairness validation on a learner profile.

        Args:
            input_dict: Must contain 'learner_information' (str), 'learner_profile' (dict),
                        and optionally 'persona_name' (str).

        Returns:
            A ProfileFairnessResult dict.
        """
        payload = FairnessValidationPayload(**input_dict)

        # Serialize learner_profile for the prompt
        prompt_vars = {
            "learner_information": payload.learner_information,
            "learner_profile": json.dumps(payload.learner_profile, indent=2),
            "persona_name": payload.persona_name or "None",
        }

        # LLM call — returns fairness_flags + overall_fairness_risk
        raw_output = self.invoke(prompt_vars, task_prompt=fairness_validator_task_prompt)

        llm_fairness_flags = raw_output.get("fairness_flags", [])
        llm_overall_risk = raw_output.get("overall_fairness_risk", "low")

        # Deterministic checks
        fslsm_deviation_flags = self._check_fslsm_deviation(
            payload.learner_profile, payload.persona_name
        )
        stereotype_flags = self._check_stereotype_keywords(payload.learner_profile)

        # Merge all flags
        all_fairness_flags = llm_fairness_flags + [
            {
                "field_name": f.dimension,
                "fairness_category": "confidence_without_evidence",
                "severity": "medium",
                "explanation": f.issue,
                "suggestion": "Verify this dimension reflects evidence from the learner's background.",
            }
            for f in fslsm_deviation_flags
        ] + stereotype_flags

        # Compute counts
        checked_fields_count = self._count_checked_fields(payload.learner_profile)
        flagged_field_names = set()
        for flag in all_fairness_flags:
            field = flag.get("field_name", "") if isinstance(flag, dict) else ""
            flagged_field_names.add(field)
        flagged_field_names.discard("")
        flagged_fields_count = len(flagged_field_names)

        # Promote risk if deterministic flags exist but LLM said low
        overall_fairness_risk = llm_overall_risk
        if (fslsm_deviation_flags or stereotype_flags) and overall_fairness_risk == "low":
            overall_fairness_risk = "medium"

        result = ProfileFairnessResult(
            fairness_flags=all_fairness_flags,
            fslsm_deviation_flags=[f.model_dump() for f in fslsm_deviation_flags],
            overall_fairness_risk=overall_fairness_risk,
            checked_fields_count=checked_fields_count,
            flagged_fields_count=flagged_fields_count,
        )
        return result.model_dump()

    @staticmethod
    def _check_fslsm_deviation(
        learner_profile: Dict[str, Any],
        persona_name: str,
    ) -> List[FSLSMDeviationFlag]:
        """Flag FSLSM dimensions that deviate significantly from persona baseline."""
        if not persona_name or persona_name not in _PERSONA_BASELINES:
            return []

        baseline = _PERSONA_BASELINES[persona_name]
        prefs = learner_profile.get("learning_preferences", {})
        dims = prefs.get("fslsm_dimensions", {})

        flags: List[FSLSMDeviationFlag] = []
        for dim_key, persona_val in baseline.items():
            profile_val = dims.get(dim_key)
            if profile_val is None:
                continue
            try:
                profile_val = float(profile_val)
            except (ValueError, TypeError):
                continue
            deviation = abs(profile_val - persona_val)
            if deviation > _FSLSM_DEVIATION_THRESHOLD:
                dim_label = _DIMENSION_NAMES.get(dim_key, dim_key)
                flags.append(
                    FSLSMDeviationFlag(
                        dimension=dim_key,
                        persona_value=persona_val,
                        profile_value=profile_val,
                        deviation=round(deviation, 2),
                        issue=(
                            f"{dim_label} shifted from persona baseline {persona_val} "
                            f"to {profile_val} (deviation {deviation:.2f}). "
                            f"Verify this change is supported by learner evidence."
                        ),
                    )
                )
        return flags

    @staticmethod
    def _check_stereotype_keywords(
        learner_profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Scan profile text fields for stereotypical language."""
        text_fields: List[tuple[str, str]] = []

        # Collect text fields to scan
        info = learner_profile.get("learner_information", "")
        if info:
            text_fields.append(("learner_information", str(info)))

        prefs = learner_profile.get("learning_preferences", {})
        notes = prefs.get("additional_notes", "")
        if notes:
            text_fields.append(("learning_preferences.additional_notes", str(notes)))

        bp = learner_profile.get("behavioral_patterns", {})
        bp_notes = bp.get("additional_notes", "")
        if bp_notes:
            text_fields.append(("behavioral_patterns.additional_notes", str(bp_notes)))

        bp_motivational = bp.get("motivational_triggers", "")
        if bp_motivational:
            text_fields.append(("behavioral_patterns.motivational_triggers", str(bp_motivational)))

        flags: List[Dict[str, Any]] = []
        for field_name, text in text_fields:
            text_lower = text.lower()
            for phrase in _STEREOTYPE_PHRASES:
                if phrase in text_lower:
                    flags.append({
                        "field_name": field_name,
                        "fairness_category": "stereotypical_language",
                        "severity": "medium",
                        "explanation": f"Field contains stereotypical phrase: '{phrase}'.",
                        "suggestion": "Remove assumption-based language and use evidence-based descriptions.",
                    })
        return flags

    @staticmethod
    def _count_checked_fields(learner_profile: Dict[str, Any]) -> int:
        """Count the number of profile fields that were checked."""
        count = 0
        # 4 FSLSM dimensions
        prefs = learner_profile.get("learning_preferences", {})
        dims = prefs.get("fslsm_dimensions", {})
        count += len(dims)
        # Cognitive status skills
        cog = learner_profile.get("cognitive_status", {})
        count += len(cog.get("mastered_skills", []))
        count += len(cog.get("in_progress_skills", []))
        # Behavioral pattern fields
        bp = learner_profile.get("behavioral_patterns", {})
        for key in ("system_usage_frequency", "session_duration_engagement", "motivational_triggers", "additional_notes"):
            if bp.get(key):
                count += 1
        return count


def validate_profile_fairness_with_llm(
    llm: Any,
    learner_information: str,
    learner_profile: dict,
    persona_name: str = "",
) -> JSONDict:
    """Convenience function: create a FairnessValidator and run validation."""
    validator = FairnessValidator(llm)
    return validator.validate_profile({
        "learner_information": learner_information,
        "learner_profile": learner_profile,
        "persona_name": persona_name,
    })
