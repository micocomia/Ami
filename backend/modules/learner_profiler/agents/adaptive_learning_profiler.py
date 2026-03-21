"""Utilities for building and updating adaptive learner profiles via LLMs."""

from __future__ import annotations

import ast
import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Union, Protocol, runtime_checkable

from base import BaseAgent
from ..schemas import LearnerProfile
from ..prompts import (
    adaptive_learner_profiler_system_prompt,
    adaptive_learner_profiler_task_prompt_initialization,
    adaptive_learner_profiler_task_prompt_update,
    adaptive_learner_profiler_task_prompt_update_cognitive,
    adaptive_learner_profiler_task_prompt_update_preferences,
    adaptive_learner_profiler_task_prompt_update_information,
)
from ..utils import (
    compose_learner_information_update_inputs,
    preserve_profile_sections_for_info_only_update,
)
from pydantic import BaseModel, Field, ValidationError, field_validator


logger = logging.getLogger(__name__)

_SOLO_LEVEL_ORDER: List[str] = ["unlearned", "beginner", "intermediate", "advanced", "expert"]
_SKILL_CONNECTOR_STOPWORDS = {"and", "the", "a", "an", "of"}


def _solo_level_value(level: Any) -> int:
    """Return the numeric rank of a SOLO level name (0 = unlearned)."""
    text = str(level or "").strip().lower()
    try:
        return _SOLO_LEVEL_ORDER.index(text)
    except ValueError:
        return 0


def _normalize_skill_name(skill_name: Any) -> str:
    """Normalize skill names for resilient matching across profile/session variants."""
    text = str(skill_name or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    parts = [
        part
        for part in re.sub(r"\s+", " ", text).strip().split(" ")
        if part and part not in _SKILL_CONNECTOR_STOPWORDS
    ]
    return " ".join(parts)


def _enforce_mastery_guardrails(
    original_profile: Mapping[str, Any],
    session_info: Mapping[str, Any],
    updated_profile: dict,
) -> dict:
    """Prevent premature promotion from in_progress_skills to mastered_skills."""
    if not isinstance(updated_profile, dict):
        return updated_profile
    if not isinstance(session_info, Mapping):
        return updated_profile
    if session_info.get("if_learned") is not True:
        return updated_profile

    original_cognitive = original_profile.get("cognitive_status", {}) if isinstance(original_profile, Mapping) else {}
    original_in_progress = original_cognitive.get("in_progress_skills", []) if isinstance(original_cognitive, Mapping) else []

    required_levels: Dict[str, int] = {}
    original_skill_data: Dict[str, dict] = {}
    original_skill_names: Dict[str, str] = {}
    for skill in original_in_progress:
        if not isinstance(skill, Mapping):
            continue
        raw_name = str(skill.get("name") or "").strip()
        normalized_name = _normalize_skill_name(raw_name)
        if not normalized_name:
            continue
        required_levels[normalized_name] = _solo_level_value(skill.get("required_proficiency_level", "beginner"))
        original_skill_data[normalized_name] = dict(skill)
        original_skill_names[normalized_name] = raw_name

    raw_outcomes = session_info.get("desired_outcome_when_completed", [])
    outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []
    session_outcome_levels: Dict[str, int] = {}
    for outcome in outcomes:
        if not isinstance(outcome, Mapping):
            continue
        normalized_name = _normalize_skill_name(outcome.get("name"))
        if not normalized_name:
            continue
        session_outcome_levels[normalized_name] = _solo_level_value(outcome.get("level", "unlearned"))

    cognitive = updated_profile.get("cognitive_status", {})
    if not isinstance(cognitive, dict):
        return updated_profile

    mastered = cognitive.get("mastered_skills", [])
    in_progress_raw = cognitive.get("in_progress_skills", [])
    if not isinstance(mastered, list) or not isinstance(in_progress_raw, list):
        return updated_profile

    in_progress = list(in_progress_raw)
    in_progress_index_by_normalized_name: Dict[str, int] = {}
    for idx, skill in enumerate(in_progress):
        if not isinstance(skill, Mapping):
            continue
        normalized_name = _normalize_skill_name(skill.get("name"))
        if normalized_name and normalized_name not in in_progress_index_by_normalized_name:
            in_progress_index_by_normalized_name[normalized_name] = idx

    kept_mastered: List[Any] = []
    changed = False

    for skill_entry in mastered:
        if not isinstance(skill_entry, Mapping):
            kept_mastered.append(skill_entry)
            continue

        raw_name = str(skill_entry.get("name") or "").strip()
        normalized_name = _normalize_skill_name(raw_name)
        if normalized_name not in required_levels:
            kept_mastered.append(skill_entry)
            continue

        required_value = required_levels[normalized_name]
        outcome_value = session_outcome_levels.get(normalized_name, -1)
        if outcome_value >= required_value:
            kept_mastered.append(skill_entry)
            continue

        changed = True
        logger.info(
            "Mastery guardrail: reverted premature promotion of '%s' (session outcome '%s' < required '%s')",
            original_skill_names.get(normalized_name, raw_name),
            _SOLO_LEVEL_ORDER[outcome_value] if outcome_value >= 0 else "unknown",
            _SOLO_LEVEL_ORDER[required_value],
        )

        target_name = original_skill_names.get(normalized_name, raw_name)
        target_required = _SOLO_LEVEL_ORDER[required_value]
        target_current = _SOLO_LEVEL_ORDER[max(0, outcome_value)]

        existing_idx = in_progress_index_by_normalized_name.get(normalized_name)
        if existing_idx is not None:
            updated_in_progress_skill = dict(in_progress[existing_idx]) if isinstance(in_progress[existing_idx], Mapping) else {}
            updated_in_progress_skill["name"] = target_name
            updated_in_progress_skill["required_proficiency_level"] = target_required
            updated_in_progress_skill["current_proficiency_level"] = target_current
            in_progress[existing_idx] = updated_in_progress_skill
        else:
            reverted_skill = dict(original_skill_data.get(normalized_name, {}))
            reverted_skill["name"] = target_name
            reverted_skill["required_proficiency_level"] = target_required
            reverted_skill["current_proficiency_level"] = target_current
            in_progress.append(reverted_skill)
            in_progress_index_by_normalized_name[normalized_name] = len(in_progress) - 1

    if not changed:
        return updated_profile

    deduped_in_progress: List[Any] = []
    seen_names = set()
    for skill in in_progress:
        if not isinstance(skill, Mapping):
            deduped_in_progress.append(skill)
            continue
        normalized_name = _normalize_skill_name(skill.get("name"))
        if normalized_name and normalized_name in seen_names:
            continue
        if normalized_name:
            seen_names.add(normalized_name)
        deduped_in_progress.append(skill)

    cognitive["mastered_skills"] = kept_mastered
    cognitive["in_progress_skills"] = deduped_in_progress
    total = len(kept_mastered) + len(deduped_in_progress)
    cognitive["overall_progress"] = round(len(kept_mastered) / total * 100) if total > 0 else 0
    updated_profile["cognitive_status"] = cognitive
    return updated_profile


class LearnerProfileInitializationPayload(BaseModel):
    """Payload for initializing a learner profile (validated)."""

    learning_goal: str = Field(...)
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]]
    skill_gaps: Union[str, Dict[str, Any], Mapping[str, Any], List[Any]]
    persona_name: str = ""
    fslsm_baseline: Dict[str, Any] = Field(default_factory=dict)

class LearnerProfileUpdatePayload(BaseModel):
    """Payload for updating an existing learner profile (validated)."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_interactions: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]]
    session_information: Optional[Union[str, Dict[str, Any], Mapping[str, Any]]] = None


class CognitiveUpdatePayload(BaseModel):
    """Payload for updating only cognitive_status based on session/quiz results."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    session_information: Union[str, Dict[str, Any], Mapping[str, Any]]


class PreferencesUpdatePayload(BaseModel):
    """Payload for updating only learning_preferences based on feedback."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_interactions: Union[str, Dict[str, Any], Mapping[str, Any]]
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]] = ""


class LearnerInformationUpdatePayload(BaseModel):
    """Payload for updating only learner_information from edits/resume."""

    learner_profile: Union[str, Dict[str, Any], Mapping[str, Any]]
    edited_learner_information: Union[str, Dict[str, Any], Mapping[str, Any]] = ""
    resume_text: Union[str, Dict[str, Any], Mapping[str, Any]] = ""
    current_learner_information: Union[str, Dict[str, Any], Mapping[str, Any]] = ""
    primary_learner_information: Union[str, Dict[str, Any], Mapping[str, Any]] = ""


class AdaptiveLearnerProfiler(BaseAgent):
    """Agent wrapper that coordinates the prompts required for learner profiling."""

    name: str = "AdaptiveLearnerProfiler"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=adaptive_learner_profiler_system_prompt,
            jsonalize_output=True,
        )

    def initialize_profile(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Generate an initial learner profile using the provided onboarding information."""
        task_prompt = adaptive_learner_profiler_task_prompt_initialization
        payload_dict = LearnerProfileInitializationPayload(**input_dict).model_dump()

        # Render persona section for the prompt template
        persona_name = payload_dict.get("persona_name", "")
        fslsm_baseline = payload_dict.get("fslsm_baseline") or {}
        if persona_name and fslsm_baseline:
            payload_dict["persona_section"] = (
                f"{persona_name} — FSLSM baseline: "
                f"processing={fslsm_baseline.get('fslsm_processing', 0)}, "
                f"perception={fslsm_baseline.get('fslsm_perception', 0)}, "
                f"input={fslsm_baseline.get('fslsm_input', 0)}, "
                f"understanding={fslsm_baseline.get('fslsm_understanding', 0)}"
            )
        elif persona_name:
            payload_dict["persona_section"] = persona_name
        else:
            payload_dict["persona_section"] = "None selected"

        # Render resume section for the prompt template
        learner_info = payload_dict.get("learner_information", "")
        if isinstance(learner_info, dict):
            raw_text = learner_info.get("raw", "") or str(learner_info)
        else:
            raw_text = str(learner_info or "")
        payload_dict["resume_section"] = raw_text.strip() if raw_text.strip() else "None provided"

        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()

    def update_profile(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing learner profile with fresh interaction data."""
        task_prompt = adaptive_learner_profiler_task_prompt_update
        payload_dict = LearnerProfileUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()

    def update_cognitive_status(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update only cognitive_status based on session/quiz results."""
        task_prompt = adaptive_learner_profiler_task_prompt_update_cognitive
        payload_dict = CognitiveUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        result = validated_output.model_dump()
        result = _enforce_mastery_guardrails(
            original_profile=payload_dict.get("learner_profile", {}),
            session_info=payload_dict.get("session_information", {}),
            updated_profile=result,
        )
        return LearnerProfile.model_validate(result).model_dump()

    def update_learning_preferences(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update only learning_preferences (and optionally behavioral_patterns)."""
        task_prompt = adaptive_learner_profiler_task_prompt_update_preferences
        payload_dict = PreferencesUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()

    def update_learner_information(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update only learner_information based on edited text/resume."""
        task_prompt = adaptive_learner_profiler_task_prompt_update_information
        payload_dict = LearnerInformationUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        base_profile = payload_dict.get("learner_profile", {})
        if not isinstance(base_profile, Mapping):
            base_profile = {}
        candidate = raw_output if isinstance(raw_output, Mapping) else {}
        merged = preserve_profile_sections_for_info_only_update(base_profile, candidate)
        validated_output = LearnerProfile.model_validate(merged)
        return validated_output.model_dump()


def initialize_learner_profile_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: Union[str, Mapping[str, Any]],
    skill_gaps: Union[str, Mapping[str, Any], List[Any]],
    persona_name: str = "",
    fslsm_baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Public helper for generating a learner profile with minimal boilerplate."""
    learner_profiler = AdaptiveLearnerProfiler(llm)
    payload_dict = {
        "learning_goal": learning_goal,
        "learner_information": learner_information,
        "skill_gaps": skill_gaps,
        "persona_name": persona_name,
        "fslsm_baseline": fslsm_baseline or {},
    }
    learner_profile = learner_profiler.initialize_profile(payload_dict)
    return learner_profile


def update_learner_profile_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any]],
    learner_information: Union[str, Mapping[str, Any]],
    session_information: Optional[Union[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Public helper for updating an existing learner profile via the LLM backend."""

    learner_profiler = AdaptiveLearnerProfiler(llm)
    payload_dict = {
        "learner_profile": learner_profile,
        "learner_interactions": learner_interactions,
        "learner_information": learner_information,
        "session_information": session_information,
    }
    return learner_profiler.update_profile(payload_dict)


def update_cognitive_status_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    session_information: Union[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Public helper for updating only cognitive_status via the LLM backend."""
    profiler = AdaptiveLearnerProfiler(llm)
    return profiler.update_cognitive_status({
        "learner_profile": learner_profile,
        "session_information": session_information,
    })


def update_learning_preferences_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    learner_interactions: Union[str, Mapping[str, Any]],
    learner_information: Union[str, Mapping[str, Any]] = "",
) -> Dict[str, Any]:
    """Public helper for updating only learning_preferences via the LLM backend."""
    profiler = AdaptiveLearnerProfiler(llm)
    return profiler.update_learning_preferences({
        "learner_profile": learner_profile,
        "learner_interactions": learner_interactions,
        "learner_information": learner_information,
    })


def update_learner_information_with_llm(
    llm: Any,
    learner_profile: Union[str, Mapping[str, Any]],
    edited_learner_information: Union[str, Mapping[str, Any]] = "",
    resume_text: Union[str, Mapping[str, Any]] = "",
) -> Dict[str, Any]:
    """Public helper for updating only learner_information via the LLM backend."""
    profiler = AdaptiveLearnerProfiler(llm)
    composed = compose_learner_information_update_inputs(
        current_learner_information=(learner_profile or {}).get("learner_information", "") if isinstance(learner_profile, Mapping) else "",
        edited_learner_information=edited_learner_information,
        resume_text=resume_text,
    )
    candidate = profiler.update_learner_information({
        "learner_profile": learner_profile,
        "edited_learner_information": composed["edited_learner_information"],
        "resume_text": composed["resume_text"],
        "current_learner_information": composed["current_learner_information"],
        "primary_learner_information": composed["primary_learner_information"],
    })
    original = learner_profile if isinstance(learner_profile, Mapping) else {}
    return preserve_profile_sections_for_info_only_update(original, candidate)
