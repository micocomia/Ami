"""Regression tests for learning path scheduler anti-repeat prompt rules."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.learning_plan_generator.prompts.learning_path_scheduling import (
    learning_path_scheduler_system_prompt,
    learning_path_scheduler_task_prompt_reflexion,
    learning_path_scheduler_task_prompt_reschedule,
)


def test_system_prompt_contains_no_repeat_level_rules():
    assert "strictly higher than that skill's current level" in learning_path_scheduler_system_prompt
    assert "Do NOT generate same-level targets" in learning_path_scheduler_system_prompt
    assert "Skills in `mastered_skills` MUST NOT be targeted" in learning_path_scheduler_system_prompt
    assert "Example (Disallowed): current `beginner` -> outcome `beginner`." in learning_path_scheduler_system_prompt
    assert "Example (Allowed): current `beginner` -> outcome `intermediate`." in learning_path_scheduler_system_prompt


def test_task_b_prompt_contains_unlearned_carveout():
    assert "if_learned=true" in learning_path_scheduler_system_prompt
    assert "enforce no-repeat-level rules only on `if_learned=false` sessions" in learning_path_scheduler_system_prompt
    assert "Refine the unlearned sessions in the learning path" in learning_path_scheduler_task_prompt_reflexion


def test_task_c_prompt_mentions_forward_progression():
    assert "strict forward progression with no same-level repeats" in learning_path_scheduler_system_prompt
    assert "Desired Session Count" in learning_path_scheduler_task_prompt_reschedule
