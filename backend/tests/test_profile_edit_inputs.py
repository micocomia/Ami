"""Tests for learner profile edit input utilities."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learner_profiler.utils.profile_edit_inputs import (
    compose_learner_information_update_inputs,
    extract_slider_override_dims,
    normalize_fslsm_slider_values,
    preserve_profile_sections_for_info_only_update,
)


def test_normalize_fslsm_slider_values_clamps_and_maps_aliases():
    normalized = normalize_fslsm_slider_values(
        {
            "processing": -1.5,
            "fslsm_perception": 0.2,
            "input": 0.99,
            "understanding": "0.7",
        }
    )
    assert normalized == {
        "fslsm_processing": -1.0,
        "fslsm_perception": 0.2,
        "fslsm_input": 0.99,
        "fslsm_understanding": 0.7,
    }


def test_extract_slider_override_dims_requires_explicit_mode():
    assert extract_slider_override_dims({"slider_values": {"processing": -0.4}}) is None
    result = extract_slider_override_dims(
        {
            "update_mode": "fslsm_slider_override",
            "slider_values": {"processing": -0.4, "perception": 0.1, "input": 0.0, "understanding": 0.5},
        }
    )
    assert result["fslsm_processing"] == -0.4
    assert result["fslsm_understanding"] == 0.5


def test_compose_learner_information_text_primary_with_truncation():
    composed = compose_learner_information_update_inputs(
        current_learner_information="Current profile text",
        edited_learner_information="Edited profile text",
        resume_text="A" * 50,
        edited_max_chars=10,
        resume_max_chars=20,
    )
    assert composed["primary_learner_information"] == "Edited pro"
    assert composed["edited_learner_information"] == "Edited pro"
    assert len(composed["resume_text"]) == 20


def test_preserve_profile_sections_for_info_only_update():
    original = {
        "learner_information": "old",
        "learning_goal": "goal",
        "goal_display_name": "display",
        "cognitive_status": {"overall_progress": 40},
        "learning_preferences": {"fslsm_dimensions": {"fslsm_input": -0.1}},
        "behavioral_patterns": {"system_usage_frequency": "daily"},
    }
    candidate = {
        "learner_information": "new",
        "learning_goal": "changed",
        "cognitive_status": {"overall_progress": 100},
    }
    result = preserve_profile_sections_for_info_only_update(original, candidate)
    assert result["learner_information"] == "new"
    assert result["learning_goal"] == "goal"
    assert result["cognitive_status"]["overall_progress"] == 40
