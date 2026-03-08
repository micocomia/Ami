from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Sequence

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.learning_plan_generator.schemas import (
    LearnerPlanFeedback,
    LLMQualityOutput,
    MAX_LEARNING_PATH_SESSIONS,
    PlanFeedbackDimensions,
)
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

_SESSION_OVERFLOW_ISSUE = (
    f"Generated path exceeded {MAX_LEARNING_PATH_SESSIONS} sessions and was truncated."
)
_SESSION_OVERFLOW_DIRECTIVE = (
    f"Regenerate a focused path that stays within {MAX_LEARNING_PATH_SESSIONS} sessions "
    "while preserving one-step SOLO progression and required proficiency coverage."
)


def _coerce_level_name(level: Any, default: str = "unlearned") -> str:
    text = str(level or "").strip().lower()
    return text if text in SOLO_LEVELS else default


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
            key = str(skill.get("name") or "").strip()
            if not key:
                continue
            level_name = _coerce_level_name(skill.get("proficiency_level"), default="unlearned")
            levels[key] = max(levels.get(key, SOLO_LEVELS["unlearned"]), SOLO_LEVELS[level_name])

    in_progress_skills = cognitive_status.get("in_progress_skills", [])
    if isinstance(in_progress_skills, Sequence) and not isinstance(in_progress_skills, (str, bytes)):
        for skill in in_progress_skills:
            if not isinstance(skill, Mapping):
                continue
            key = str(skill.get("name") or "").strip()
            if not key:
                continue
            level_name = _coerce_level_name(skill.get("current_proficiency_level"), default="unlearned")
            levels[key] = max(levels.get(key, SOLO_LEVELS["unlearned"]), SOLO_LEVELS[level_name])

    return levels


def build_deterministic_solo_audit(learner_profile: Any, learning_path: Any) -> Dict[str, Any]:
    current_levels = _build_baseline_skill_levels(learner_profile)
    initial_levels = dict(current_levels)
    logger.debug("[SOLO_AUDIT] initial_levels=%s", initial_levels)
    logger.debug("[SOLO_AUDIT] learning_path type=%s len=%s", type(learning_path).__name__, len(learning_path) if hasattr(learning_path, "__len__") else "?")
    baseline_levels = {
        skill: SOLO_LEVEL_NAMES[level]
        for skill, level in sorted(current_levels.items(), key=lambda item: item[0])
    }

    transitions: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []

    # Inline: _extract_path_sessions
    sessions_raw: Any = learning_path
    if isinstance(learning_path, Mapping):
        sessions_raw = learning_path.get("learning_path", [])
    if not isinstance(sessions_raw, Sequence) or isinstance(sessions_raw, (str, bytes)):
        sessions_raw = []
    sessions = [s for s in sessions_raw if isinstance(s, Mapping)]

    for session_index, session in enumerate(sessions, start=1):
        outcomes = session.get("desired_outcome_when_completed", [])
        if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
            continue
        session_id = str(session.get("id", f"Session {session_index}"))
        session_title = str(session.get("title", "")).strip()
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                logger.debug("[SOLO_AUDIT] session %s: outcome is not a Mapping (type=%s): %r", session_id, type(outcome).__name__, outcome)
                continue
            skill_key = str(outcome.get("name") or "").strip()
            if not skill_key:
                continue
            from_value = current_levels.get(skill_key, SOLO_LEVELS["unlearned"])
            to_level_name = _coerce_level_name(outcome.get("level"), default="unlearned")
            to_value = SOLO_LEVELS[to_level_name]
            delta = to_value - from_value
            transition = {
                "session_index": session_index,
                "session_id": session_id,
                "session_title": session_title,
                "skill": skill_key,
                "from_level": SOLO_LEVEL_NAMES[from_value],
                "to_level": to_level_name,
                "delta": delta,
                "is_violation": delta > 1,
            }
            transitions.append(transition)
            if delta > 1:
                violations.append(transition)
            current_levels[skill_key] = max(from_value, to_value)

    logger.debug("[SOLO_AUDIT] transitions=%s", [(t["skill"], t["from_level"], t["to_level"]) for t in transitions])

    # Inline: _build_coverage_gaps
    coverage_gaps: List[Dict[str, Any]] = []
    if isinstance(learner_profile, Mapping):
        cognitive_status = learner_profile.get("cognitive_status", {})
        in_progress_skills = cognitive_status.get("in_progress_skills", []) if isinstance(cognitive_status, Mapping) else []
        if isinstance(in_progress_skills, Sequence) and not isinstance(in_progress_skills, (str, bytes)):
            for skill in in_progress_skills:
                if not isinstance(skill, Mapping):
                    continue
                skill_key = str(skill.get("name") or "").strip()
                if not skill_key:
                    continue
                required_level_name = _coerce_level_name(skill.get("required_proficiency_level"), default="beginner")
                required_value = SOLO_LEVELS[required_level_name]
                initial_value = initial_levels.get(skill_key, SOLO_LEVELS["unlearned"])
                if required_value <= initial_value:
                    continue
                missing_levels = [
                    SOLO_LEVEL_NAMES[lvl]
                    for lvl in range(initial_value + 1, required_value + 1)
                    if not any(
                        t["skill"] == skill_key and t["to_level"] == SOLO_LEVEL_NAMES[lvl]
                        for t in transitions
                    )
                ]
                if missing_levels:
                    logger.debug(
                        "[SOLO_AUDIT] coverage gap: skill=%r initial=%s required=%s missing=%s transitions_for_skill=%s",
                        skill_key, SOLO_LEVEL_NAMES[initial_value], required_level_name, missing_levels,
                        [(t["skill"], t["to_level"]) for t in transitions if t["skill"] == skill_key],
                    )
                    reached_value = current_levels.get(skill_key, initial_value)
                    coverage_gaps.append({
                        "skill": skill_key,
                        "current_level": SOLO_LEVEL_NAMES[initial_value],
                        "required_level": required_level_name,
                        "reached_level": SOLO_LEVEL_NAMES[reached_value],
                        "missing_levels": missing_levels,
                    })

    return {
        "policy": "No skill may advance by more than one SOLO level in a single session step.",
        "level_order": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
        "baseline_levels": baseline_levels,
        "transitions": transitions,
        "violations": violations,
        "violation_count": len(violations),
        "has_violations": bool(violations),
        "coverage_gaps": coverage_gaps,
        "coverage_gap_count": len(coverage_gaps),
        "has_coverage_gaps": bool(coverage_gaps),
    }


def _merge_feedback(
    llm_output: LLMQualityOutput,
    solo_audit: Mapping[str, Any],
    generation_observations: Mapping[str, Any],
) -> LearnerPlanFeedback:
    violations = solo_audit.get("violations", [])
    violation_count = int(solo_audit.get("violation_count", 0) or 0)
    coverage_gaps = solo_audit.get("coverage_gaps", [])
    coverage_gap_count = int(solo_audit.get("coverage_gap_count", 0) or 0)

    # Inline: _detect_session_overflow
    has_overflow = False
    if isinstance(generation_observations, Mapping):
        has_overflow = bool(generation_observations.get("was_trimmed", False))
        if not has_overflow:
            try:
                has_overflow = int(generation_observations.get("raw_session_count", 0)) > MAX_LEARNING_PATH_SESSIONS
            except (TypeError, ValueError):
                pass

    structural_issues: List[str] = []
    structural_directives = ""

    # Inline: _build_violation_issues + _build_violation_directives
    if violation_count > 0:
        count = len(violations)
        structural_issues.append(f"SOLO progression skipped for {count} skill transition(s)")
        first = violations[0]
        sid = str(first.get("session_id", "")).strip() or f"Session {first.get('session_index', '?')}"
        skill = str(first.get("skill", "a skill")).strip() or "a skill"
        structural_issues.append(
            f"{sid} advances '{skill}' from {first.get('from_level', 'unlearned')} to {first.get('to_level', 'advanced')} in one step"
        )
        steps = []
        for v in violations[:3]:
            vsid = str(v.get("session_id", "")).strip() or f"Session {v.get('session_index', '?')}"
            vskill = str(v.get("skill", "skill")).strip() or "skill"
            steps.append(f"{vsid} '{vskill}': {v.get('from_level', 'unlearned')} -> {v.get('to_level', 'advanced')}")
        structural_directives = (
            "Insert bridging sessions so each skill advances by at most one SOLO level per session "
            f"(unlearned -> beginner -> intermediate -> advanced -> expert). Fix these transitions: {'; '.join(steps)}."
        )

    if coverage_gap_count > 0:
        for gap in coverage_gaps[:2]:
            structural_issues.append(
                f"Path for '{gap.get('skill', 'a skill')}' only reaches '{gap.get('reached_level', '?')}' "
                f"but required level is '{gap.get('required_level', '?')}'"
            )
        if not structural_directives:
            gap_details = "; ".join(
                f"'{g.get('skill')}' needs {' -> '.join(g.get('missing_levels', []))}"
                for g in coverage_gaps[:2]
            )
            structural_directives = (
                f"Coverage gaps detected for: {gap_details}. "
                "For each missing skill, ensure that at least one session explicitly lists that skill "
                "in `desired_outcome_when_completed` with the correct target level. "
                "If a session already covers the skill topically, update its `desired_outcome_when_completed` "
                "to include the skill's exact name from `in_progress_skills` and the appropriate level. "
                "Advance one SOLO level per session."
            )

    if has_overflow:
        structural_issues.insert(0, _SESSION_OVERFLOW_ISSUE)
        if not structural_directives:
            structural_directives = _SESSION_OVERFLOW_DIRECTIVE
        elif _SESSION_OVERFLOW_DIRECTIVE not in structural_directives:
            structural_directives = f"{_SESSION_OVERFLOW_DIRECTIVE} {structural_directives}".strip()

    # Progression feedback is always set from audit (not LLM)
    feedback_data = llm_output.feedback.model_dump()   # progression defaults to ""
    suggestions_data = llm_output.suggestions.model_dump()   # progression defaults to ""

    if violation_count > 0:
        feedback_data["progression"] = (
            "The learner would likely struggle with progression because deterministic SOLO audit found "
            f"{violation_count} level-skipping transition(s)."
        )
        suggestions_data["progression"] = (
            "Insert bridging sessions so each skill advances by at most one SOLO level per session."
        )
    elif coverage_gap_count > 0:
        feedback_data["progression"] = (
            "The learner's path does not fully cover all required proficiency levels; "
            f"deterministic SOLO audit found {coverage_gap_count} skill(s) with missing coverage."
        )
        suggestions_data["progression"] = (
            "Add sessions for each missing SOLO level so every required proficiency is explicitly targeted."
        )
    else:
        feedback_data["progression"] = (
            "The learner would likely find progression coherent; deterministic SOLO audit found no "
            "level-skipping transitions."
        )
        suggestions_data["progression"] = (
            "Maintain one-step SOLO progression per skill while refining engagement and personalization as needed."
        )

    quality_issues = [str(i).strip() for i in llm_output.quality_issues if str(i).strip()]

    # Inline: _dedupe_nonempty + cap at 3
    seen: set = set()
    all_issues: List[str] = []
    for item in structural_issues + quality_issues:
        if item and item not in seen:
            seen.add(item)
            all_issues.append(item)
    all_issues = all_issues[:3]

    improvement_directives = structural_directives or llm_output.quality_directives.strip()
    is_acceptable = (
        violation_count == 0
        and coverage_gap_count == 0
        and not has_overflow
        and not quality_issues
    )

    return LearnerPlanFeedback(
        feedback=PlanFeedbackDimensions(**feedback_data),
        suggestions=PlanFeedbackDimensions(**suggestions_data),
        is_acceptable=is_acceptable,
        issues=all_issues,
        improvement_directives=improvement_directives,
    )


class LearningPathFeedbackPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_path: Any
    generation_observations: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("learner_profile", "learning_path", "generation_observations")
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

    def feedback_path(self, payload: LearningPathFeedbackPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, LearningPathFeedbackPayload):
            payload = LearningPathFeedbackPayload.model_validate(payload)

        # Evaluate only sessions the learner still has to complete.
        # Completed sessions (if_learned=True) reflect the old FSLSM profile and
        # would bias engagement/personalization feedback toward stale preferences.
        _raw = payload.learning_path
        if isinstance(_raw, Mapping):
            _sessions = _raw.get("learning_path", [])
        elif isinstance(_raw, list):
            _sessions = _raw
        else:
            _sessions = []
        unlearned_path = [
            s for s in _sessions
            if isinstance(s, Mapping) and not s.get("if_learned", False)
        ]

        profile_for_eval = {
            k: v for k, v in payload.learner_profile.items()
            if k != "learner_information"
        }

        solo_audit = build_deterministic_solo_audit(
            learner_profile=profile_for_eval,
            learning_path=unlearned_path,
        )
        invoke_payload = payload.model_dump()
        invoke_payload["learner_profile"] = profile_for_eval
        invoke_payload["learning_path"] = unlearned_path
        invoke_payload["solo_audit"] = solo_audit
        raw_output = self.invoke(invoke_payload, task_prompt=plan_feedback_simulator_task_prompt)
        llm_output = LLMQualityOutput.model_validate(raw_output)
        return _merge_feedback(llm_output, solo_audit, payload.generation_observations).model_dump()


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
