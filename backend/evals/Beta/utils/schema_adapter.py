"""Schema normalization helpers for Beta evals."""

import json
import re


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def extract_skill_gaps_summary(skill_gap_body: dict) -> str:
    return json.dumps(skill_gap_body.get("skill_gaps", []), indent=2)


def extract_skill_requirements_summary(skill_gap_body: dict) -> str:
    return json.dumps(skill_gap_body.get("skill_requirements", []), indent=2)


def extract_refined_goal(skill_gap_body: dict) -> str:
    if "refined_goal" in skill_gap_body:
        return skill_gap_body["refined_goal"]
    goal_assessment = extract_goal_assessment(skill_gap_body)
    if isinstance(goal_assessment, dict):
        refined = goal_assessment.get("refined_goal")
        if refined:
            return refined
    return skill_gap_body.get("learning_goal", "")


def extract_goal_assessment(skill_gap_body: dict) -> dict:
    return _as_dict(skill_gap_body.get("goal_assessment", {}))


def extract_goal_context(skill_gap_body: dict) -> dict:
    return _as_dict(skill_gap_body.get("goal_context", {}))


def extract_retrieved_sources(skill_gap_body: dict) -> list[dict]:
    sources = skill_gap_body.get("retrieved_sources", [])
    return [item for item in sources if isinstance(item, dict)] if isinstance(sources, list) else []


def extract_learning_path_summary(path_body: dict) -> str:
    return json.dumps(path_body.get("learning_path", []), indent=2)


def extract_fslsm_dimensions(profile_body: dict) -> dict | None:
    prefs = profile_body.get("learning_preferences", {})
    if isinstance(prefs, dict):
        dims = prefs.get("fslsm_dimensions")
        if dims:
            return dims
    return None


def extract_current_solo_level(profile_body: dict) -> str:
    cog = profile_body.get("cognitive_status", {})
    if not isinstance(cog, dict):
        return "unknown"
    in_progress = cog.get("in_progress_skills", [])
    if in_progress:
        levels = [
            item.get("current_proficiency_level", item.get("current_level", "unlearned"))
            for item in in_progress
            if isinstance(item, dict)
        ]
        if levels:
            return max(set(levels), key=levels.count)
    return "unlearned"


def extract_quiz_counts(quizzes: dict) -> dict:
    quiz_body = _as_dict(quizzes)
    return {
        key: len(value) if isinstance(value, list) else 0
        for key, value in quiz_body.items()
        if key.endswith("_questions")
    }


def detect_content_contract_signals(content_md: str) -> dict:
    text = str(content_md or "")
    return {
        "has_checkpoint_challenge": "checkpoint challenge" in text.lower(),
        "has_reflection_pause": "reflection pause" in text.lower() or "reflection period" in text.lower(),
        "has_mermaid_diagram": "```mermaid" in text.lower(),
        "has_markdown_table": bool(re.search(r"^\|.+\|$", text, flags=re.MULTILINE)),
        "is_tts_friendly": all(marker not in text.lower() for marker in ("see above", "as shown above", "see the diagram")),
    }
