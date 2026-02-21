"""Utilities for building and updating adaptive learner profiles via LLMs."""

from __future__ import annotations

import ast
import logging
from typing import Any, Dict, List, Mapping, Optional, Union, Protocol, runtime_checkable

from base import BaseAgent
from ..schemas import LearnerProfile
from ..prompts import (
    adaptive_learner_profiler_system_prompt,
    adaptive_learner_profiler_task_prompt_initialization,
    adaptive_learner_profiler_task_prompt_update,
    adaptive_learner_profiler_task_prompt_update_cognitive,
    adaptive_learner_profiler_task_prompt_update_preferences,
)
from pydantic import BaseModel, Field, ValidationError, field_validator


logger = logging.getLogger(__name__)


class LearnerProfileInitializationPayload(BaseModel):
    """Payload for initializing a learner profile (validated)."""

    learning_goal: str = Field(...)
    learner_information: Union[str, Dict[str, Any], Mapping[str, Any]]
    skill_gaps: Union[str, Dict[str, Any], Mapping[str, Any], List[Any]]

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
        return validated_output.model_dump()

    def update_learning_preferences(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update only learning_preferences (and optionally behavioral_patterns)."""
        task_prompt = adaptive_learner_profiler_task_prompt_update_preferences
        payload_dict = PreferencesUpdatePayload(**input_dict).model_dump()
        raw_output = self.invoke(payload_dict, task_prompt=task_prompt)
        validated_output = LearnerProfile.model_validate(raw_output)
        return validated_output.model_dump()


def initialize_learner_profile_with_llm(
    llm: Any,
    learning_goal: str,
    learner_information: Union[str, Mapping[str, Any]],
    skill_gaps: Union[str, Mapping[str, Any], List[Any]],
) -> Dict[str, Any]:
    """Public helper for generating a learner profile with minimal boilerplate."""
    learner_profiler = AdaptiveLearnerProfiler(llm)
    payload_dict = {
        "learning_goal": learning_goal,
        "learner_information": learner_information,
        "skill_gaps": skill_gaps,
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
