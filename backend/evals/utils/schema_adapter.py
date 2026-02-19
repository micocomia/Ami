"""
Schema normalization helpers.

GenMentor and the enhanced version share the same endpoint contracts for the
core pipeline but produce different output schemas.  These helpers extract a
common representation that the LLM-judge prompts can use for both versions.
"""

import json
from typing import Any


def extract_skill_gaps_summary(skill_gap_body: dict) -> str:
    """
    Return a JSON string summarising skill gaps from either version's
    /identify-skill-gap-with-info response.
    Both versions return a top-level 'skill_gaps' list.
    """
    gaps = skill_gap_body.get("skill_gaps", [])
    return json.dumps(gaps, indent=2)


def extract_skill_requirements_summary(skill_gap_body: dict) -> str:
    reqs = skill_gap_body.get("skill_requirements", [])
    return json.dumps(reqs, indent=2)


def extract_refined_goal(skill_gap_body: dict) -> str:
    """
    Both versions embed the refined goal inside the skill gap response.
    Field name differs: GenMentor uses 'refined_goal', enhanced may use
    'goal_assessment.refined_goal'. Fall back to raw learning_goal if absent.
    """
    if "refined_goal" in skill_gap_body:
        return skill_gap_body["refined_goal"]
    goal_assessment = skill_gap_body.get("goal_assessment", {})
    if isinstance(goal_assessment, dict) and "refined_goal" in goal_assessment:
        return goal_assessment["refined_goal"]
    return skill_gap_body.get("learning_goal", "")


def extract_learning_path_summary(path_body: dict) -> str:
    path = path_body.get("learning_path", [])
    return json.dumps(path, indent=2)


def extract_fslsm_dimensions(profile_body: dict) -> dict | None:
    """
    Return FSLSM dimensions dict from enhanced profile, or None for GenMentor.
    """
    prefs = profile_body.get("learning_preferences", {})
    if isinstance(prefs, dict):
        dims = prefs.get("fslsm_dimensions")
        if dims:
            return dims
    return None


def extract_current_solo_level(profile_body: dict) -> str:
    """
    Best-effort extraction of the dominant current SOLO level from cognitive_status.
    Returns a plain-English string for the judge prompt.
    """
    cog = profile_body.get("cognitive_status", {})
    if not isinstance(cog, dict):
        return "unknown"
    in_progress = cog.get("in_progress_skills", [])
    if in_progress:
        levels = [s.get("current_level", "unlearned") for s in in_progress]
        # Return the modal level
        return max(set(levels), key=levels.count)
    return "unlearned"
