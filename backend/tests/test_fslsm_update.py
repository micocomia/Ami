"""Verify that FSLSM dimension vectors shift after a profile update.

Run from the repo root:
    python -m pytest backend/tests/test_fslsm_update.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from base.llm_factory import LLMFactory
from modules.learner_profiler.agents.adaptive_learning_profiler import (
    update_learner_profile_with_llm,
)

BEFORE_PROFILE = {
    "learner_information": "MBA grad with admin background",
    "learning_goal": "Become an HR Manager",
    "cognitive_status": {
        "overall_progress": 20,
        "mastered_skills": [
            {"name": "Communication", "proficiency_level": "advanced"}
        ],
        "in_progress_skills": [
            {
                "name": "HRIS Management",
                "required_proficiency_level": "intermediate",
                "current_proficiency_level": "unlearned",
            }
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": 0.0,
            "fslsm_perception": 0.0,
            "fslsm_input": 0.0,
            "fslsm_understanding": 0.0,
        }
    },
    "behavioral_patterns": {
        "system_usage_frequency": "2 logins/week",
        "session_duration_engagement": "20 min avg",
    },
}

# Interaction that strongly signals: active, visual, sequential
INTERACTIONS = {
    "feedback": (
        "I loved the hands-on exercises and video walkthroughs. "
        "Step-by-step labs are way more effective for me than reading theory."
    )
}


@pytest.fixture()
def llm():
    return LLMFactory.create(model="gpt-4o", model_provider="openai")


class TestFSLSMUpdate:
    def test_at_least_one_dimension_changes(self, llm):
        """After a profile update, at least one FSLSM dimension should shift."""
        after = update_learner_profile_with_llm(
            llm, BEFORE_PROFILE, INTERACTIONS, "", None
        )

        dims_before = BEFORE_PROFILE["learning_preferences"]["fslsm_dimensions"]
        dims_after = after["learning_preferences"]["fslsm_dimensions"]

        changed = any(dims_before[k] != dims_after[k] for k in dims_before)
        assert changed, "No FSLSM dimensions changed. The LLM may not be following the prompt."

    def test_dimensions_within_valid_range(self, llm):
        """All FSLSM dimension values must be in [-1, 1]."""
        after = update_learner_profile_with_llm(
            llm, BEFORE_PROFILE, INTERACTIONS, "", None
        )

        dims_after = after["learning_preferences"]["fslsm_dimensions"]
        for key, val in dims_after.items():
            assert -1 <= val <= 1, f"{key} out of range: {val}"
