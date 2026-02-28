from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Mapping, Sequence

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.learning_plan_generator.schemas import LearnerPlanFeedback
from modules.learning_plan_generator.prompts.plan_feedback import (
    plan_feedback_simulator_system_prompt,
    plan_feedback_simulator_task_prompt,
)

logger = logging.getLogger(__name__)

SOLO_LEVELS: Dict[str, int] = {
    "unlearned": 0,
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
    "expert": 4,
}
SOLO_LEVEL_NAMES = {v: k for k, v in SOLO_LEVELS.items()}

_PROGRESSION_KEYWORDS = (
    "solo",
    "progression",
    "pace",
    "pacing",
    "too fast",
    "abrupt",
    "jump",
    "skip",
    "skipped",
    "foundational",
    "beginner level",
)

_NON_PROGRESSION_HINTS = (
    "engagement",
    "personalization",
    "preference",
    "fslsm",
    "checkpoint",
    "navigation",
    "reflection",
    "visual",
    "verbal",
    "active",
    "reflective",
)

_POSITIVE_PROGRESSION_HINTS = (
    "well-paced",
    "well paced",
    "coherent",
    "logical flow",
    "smooth progression",
    "appropriate pace",
    "scaffolded",
)

_SKILL_CONNECTOR_STOPWORDS = {"and", "the", "a", "an", "of"}


def _normalize_skill_name(skill_name: Any) -> str:
    text = str(skill_name or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    parts = [p for p in re.sub(r"\s+", " ", text).strip().split(" ") if p and p not in _SKILL_CONNECTOR_STOPWORDS]
    return " ".join(parts)


def _coerce_level_name(level: Any, default: str = "unlearned") -> str:
    text = str(level or "").strip().lower()
    return text if text in SOLO_LEVELS else default


def _extract_path_sessions(learning_path: Any) -> List[Mapping[str, Any]]:
    sessions: Any = learning_path
    if isinstance(learning_path, Mapping):
        sessions = learning_path.get("learning_path", [])

    if not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes)):
        return []

    out: List[Mapping[str, Any]] = []
    for session in sessions:
        if isinstance(session, Mapping):
            out.append(session)
    return out


def _build_baseline_skill_levels(learner_profile: Any) -> Dict[str, int]:
    if not isinstance(learner_profile, Mapping):
        return {}

    cognitive_status = learner_profile.get("cognitive_status", {})
    if not isinstance(cognitive_status, Mapping):
        return {}

    levels: Dict[str, int] = {}

    mastered_skills = cognitive_status.get("mastered_skills", [])
    if isinstance(mastered_skills, Sequence) and not isinstance(mastered_skills, (str, bytes)):
        for skill in mastered_skills:
            if not isinstance(skill, Mapping):
                continue
            key = _normalize_skill_name(skill.get("name"))
            if not key:
                continue
            level_name = _coerce_level_name(skill.get("proficiency_level"), default="unlearned")
            levels[key] = max(levels.get(key, SOLO_LEVELS["unlearned"]), SOLO_LEVELS[level_name])

    in_progress_skills = cognitive_status.get("in_progress_skills", [])
    if isinstance(in_progress_skills, Sequence) and not isinstance(in_progress_skills, (str, bytes)):
        for skill in in_progress_skills:
            if not isinstance(skill, Mapping):
                continue
            key = _normalize_skill_name(skill.get("name"))
            if not key:
                continue
            level_name = _coerce_level_name(skill.get("current_proficiency_level"), default="unlearned")
            levels[key] = max(levels.get(key, SOLO_LEVELS["unlearned"]), SOLO_LEVELS[level_name])

    return levels


def build_deterministic_solo_audit(learner_profile: Any, learning_path: Any) -> Dict[str, Any]:
    current_levels = _build_baseline_skill_levels(learner_profile)
    baseline_levels = {
        skill: SOLO_LEVEL_NAMES[level] for skill, level in sorted(current_levels.items(), key=lambda item: item[0])
    }

    transitions: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []

    sessions = _extract_path_sessions(learning_path)
    for session_index, session in enumerate(sessions, start=1):
        outcomes = session.get("desired_outcome_when_completed", [])
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            continue

        session_id = str(session.get("id", f"Session {session_index}"))
        session_title = str(session.get("title", "")).strip()

        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                continue

            raw_skill_name = outcome.get("name")
            normalized_skill = _normalize_skill_name(raw_skill_name)
            if not normalized_skill:
                continue

            from_value = current_levels.get(normalized_skill, SOLO_LEVELS["unlearned"])
            to_level_name = _coerce_level_name(outcome.get("level"), default="unlearned")
            to_value = SOLO_LEVELS[to_level_name]
            delta = to_value - from_value

            transition = {
                "session_index": session_index,
                "session_id": session_id,
                "session_title": session_title,
                "skill": str(raw_skill_name or "").strip(),
                "normalized_skill": normalized_skill,
                "from_level": SOLO_LEVEL_NAMES[from_value],
                "to_level": to_level_name,
                "delta": delta,
                "is_violation": delta > 1,
            }
            transitions.append(transition)

            if delta > 1:
                violations.append(transition)

            # Same-level/downward transitions are allowed; keep highest reached level for future checks.
            current_levels[normalized_skill] = max(from_value, to_value)

    return {
        "policy": "No skill may advance by more than one SOLO level in a single session step.",
        "level_order": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
        "baseline_levels": baseline_levels,
        "transitions": transitions,
        "violations": violations,
        "violation_count": len(violations),
        "has_violations": bool(violations),
    }


def _contains_any_keyword(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def _is_progression_issue(issue_text: str) -> bool:
    return _contains_any_keyword(issue_text, _PROGRESSION_KEYWORDS)


def _progression_claims_problem(text: str) -> bool:
    return _contains_any_keyword(text, _PROGRESSION_KEYWORDS)


def _progression_claims_positive(text: str) -> bool:
    return _contains_any_keyword(text, _POSITIVE_PROGRESSION_HINTS)


def _is_progression_only_directive(text: str) -> bool:
    if not text.strip():
        return False
    has_progression = _contains_any_keyword(text, _PROGRESSION_KEYWORDS)
    has_non_progression = _contains_any_keyword(text, _NON_PROGRESSION_HINTS)
    return has_progression and not has_non_progression


def _dedupe_nonempty(items: Sequence[str]) -> List[str]:
    seen = set()
    deduped: List[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _build_violation_issues(violations: Sequence[Mapping[str, Any]]) -> List[str]:
    if not violations:
        return []
    count = len(violations)
    issues = [f"SOLO progression skipped for {count} skill transition(s)"]
    first = violations[0]
    session_id = str(first.get("session_id", "")).strip() or f"Session {first.get('session_index', '?')}"
    skill = str(first.get("skill", "a skill")).strip() or "a skill"
    from_level = str(first.get("from_level", "unlearned")).strip()
    to_level = str(first.get("to_level", "advanced")).strip()
    issues.append(
        f"{session_id} advances '{skill}' from {from_level} to {to_level} in one step"
    )
    return issues


def _build_violation_directives(violations: Sequence[Mapping[str, Any]]) -> str:
    if not violations:
        return ""

    steps: List[str] = []
    for violation in violations[:3]:
        session_id = str(violation.get("session_id", "")).strip() or f"Session {violation.get('session_index', '?')}"
        skill = str(violation.get("skill", "skill")).strip() or "skill"
        from_level = str(violation.get("from_level", "unlearned")).strip()
        to_level = str(violation.get("to_level", "advanced")).strip()
        steps.append(f"{session_id} '{skill}': {from_level} -> {to_level}")

    details = "; ".join(steps)
    return (
        "Insert bridging sessions so each skill advances by at most one SOLO level per session "
        "(unlearned -> beginner -> intermediate -> advanced -> expert). "
        f"Fix these transitions: {details}."
    )


def reconcile_feedback_with_solo_audit(
    feedback: LearnerPlanFeedback,
    solo_audit: Mapping[str, Any],
) -> LearnerPlanFeedback:
    data = feedback.model_dump()
    had_override = False

    issues = _dedupe_nonempty(data.get("issues", []))
    directives = str(data.get("improvement_directives", "") or "").strip()
    violations = solo_audit.get("violations", [])
    violation_count = int(solo_audit.get("violation_count", 0) or 0)

    if not isinstance(violations, list):
        violations = []
        violation_count = 0

    feedback_progression = str(data.get("feedback", {}).get("progression", "") or "").strip()
    suggestion_progression = str(data.get("suggestions", {}).get("progression", "") or "").strip()

    if violation_count == 0:
        filtered_issues = [issue for issue in issues if not _is_progression_issue(issue)]
        if len(filtered_issues) != len(issues):
            had_override = True
            issues = filtered_issues

        if directives and _is_progression_only_directive(directives):
            directives = ""
            had_override = True

        if feedback_progression and _progression_claims_problem(feedback_progression):
            data["feedback"]["progression"] = (
                "The learner would likely find progression coherent; deterministic SOLO audit found no "
                "level-skipping transitions."
            )
            had_override = True

        if suggestion_progression and _progression_claims_problem(suggestion_progression):
            data["suggestions"]["progression"] = (
                "Maintain one-step SOLO progression per skill while refining engagement and personalization as needed."
            )
            had_override = True

        if not issues and data.get("is_acceptable") is not True:
            data["is_acceptable"] = True
            had_override = True
    else:
        if data.get("is_acceptable") is not False:
            data["is_acceptable"] = False
            had_override = True

        if not any(_is_progression_issue(issue) for issue in issues):
            issues.extend(_build_violation_issues(violations))
            had_override = True

        if not directives or not _progression_claims_problem(directives):
            directives = _build_violation_directives(violations)
            had_override = True

        if not feedback_progression or _progression_claims_positive(feedback_progression):
            data["feedback"]["progression"] = (
                "The learner would likely struggle with progression because deterministic SOLO audit found "
                f"{violation_count} level-skipping transition(s)."
            )
            had_override = True

        if not suggestion_progression or not _progression_claims_problem(suggestion_progression):
            data["suggestions"]["progression"] = (
                "Insert bridging sessions so each skill advances by at most one SOLO level per session."
            )
            had_override = True

    issues = _dedupe_nonempty(issues)
    if len(issues) > 3:
        issues = issues[:3]
    data["issues"] = issues
    data["improvement_directives"] = directives

    reconciled = LearnerPlanFeedback.model_validate(data)
    if had_override:
        logger.info(
            "Reconciled plan feedback against deterministic SOLO audit (violations=%d)",
            violation_count,
        )
    return reconciled


class LearningPathFeedbackPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_path: Any

    @field_validator("learner_profile", "learning_path")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v


class LearningPlanFeedbackSimulator(BaseAgent):

    name: str = "LearningPlanFeedbackSimulator"

    def __init__(self, model: Any) -> None:
        super().__init__(
            model=model,
            system_prompt=plan_feedback_simulator_system_prompt,
            jsonalize_output=True,
        )

    @staticmethod
    def _normalize_feedback_output(raw_output: Any) -> dict:
        if not isinstance(raw_output, Mapping):
            return raw_output
        normalized = dict(raw_output)
        directives = normalized.get("improvement_directives", "")
        if isinstance(directives, list):
            normalized["improvement_directives"] = "\n".join(
                str(item).strip() for item in directives if str(item).strip()
            )
        elif directives is None:
            normalized["improvement_directives"] = ""
        elif not isinstance(directives, str):
            normalized["improvement_directives"] = str(directives).strip()
        return normalized

    def feedback_path(self, payload: LearningPathFeedbackPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, LearningPathFeedbackPayload):
            payload = LearningPathFeedbackPayload.model_validate(payload)

        solo_audit = build_deterministic_solo_audit(
            learner_profile=payload.learner_profile,
            learning_path=payload.learning_path,
        )
        invoke_payload = payload.model_dump()
        invoke_payload["solo_audit"] = solo_audit

        raw_output = self.invoke(invoke_payload, task_prompt=plan_feedback_simulator_task_prompt)
        raw_output = self._normalize_feedback_output(raw_output)
        validated_output = LearnerPlanFeedback.model_validate(raw_output)
        reconciled_output = reconcile_feedback_with_solo_audit(validated_output, solo_audit)
        return reconciled_output.model_dump()


def simulate_path_feedback_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_path: Any,
) -> dict:
    """Simulate learner feedback on a learning path."""
    simulator = LearningPlanFeedbackSimulator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
    }
    return simulator.feedback_path(payload)
