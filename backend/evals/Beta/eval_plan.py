"""Learning plan evaluation for the current backend."""

import ast
import json
import os
import re

import httpx

from evals.Beta.auth import bootstrap_auth_headers
from evals.Beta.config import (
    BETA_BASE_URL,
    DATASETS_DIR,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    DEFAULT_SESSION_COUNT,
    RESULTS_DIR,
    VERSION_KEY,
    VERSION_LABEL,
)
from evals.Beta.metric_metadata import get_category_metadata, get_metric_metadata
from evals.Beta.utils.llm_judge import average_score, judge
from evals.Beta.utils.schema_adapter import (
    extract_fslsm_dimensions,
    extract_learning_path_summary,
    extract_skill_gaps_summary,
)

SHARED_JUDGE_SYSTEM = """\
You are an expert instructional designer evaluating a personalized learning plan.
Rate the plan on the specified dimensions using a 1-5 scale.
Respond ONLY with valid JSON matching the schema in the user prompt."""

SHARED_JUDGE_USER = """\
Learner Background: {learner_information}
Learning Goal: {learning_goal}
Skill Gaps to Address:
{skill_gaps}
Requested Session Count: {session_count}
Learner Profile FSLSM Dimensions:
{fslsm}
Generated Learning Path (exact JSON):
{learning_path}
Deterministic SOLO Audit:
{plan_audit}
FSLSM Structural Flag Signals:
{fslsm_structural_signals}
Abstract-to-Flag Consistency Signals:
{flag_signals}
Session Abstract SOLO Signals:
{abstract_solo_signals}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "pedagogical_sequencing": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "skill_coverage": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "scope_appropriateness": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "session_abstraction_quality": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "fslsm_structural_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_outcome_progression": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring guidance:
- pedagogical_sequencing: high only if prerequisite order is sensible and the path obeys one-step SOLO progression without skipping.
    Score 5: sessions build on each other correctly, prerequisites appear before dependent skills, and the path obeys one-step SOLO progression with no illegal skips.
    Score 4: sequencing is mostly correct with only minor ordering issues that do not materially block progression, and the path still respects the stepwise progression contract.
    Score 3: sequencing is mixed — some prerequisites are in place, but multiple sessions are awkwardly ordered or only loosely structured.
    Score 2: sequencing is poor — prerequisite violations or progression problems are frequent enough to confuse most learners.
    Score 1: sessions are ordered with no regard for prerequisites or legal progression, with advanced material appearing before foundations are established.
- skill_coverage: high only if every in-progress skill is covered enough times to reach its required level one step at a time, and appears verbatim in desired outcomes.
    Score 5: every in-progress skill is explicitly covered, appears verbatim in desired outcomes, and is advanced one level at a time until the required level is reached.
    Score 4: almost all required skills are fully covered, with only one minor coverage weakness or lightly underdeveloped progression.
    Score 3: coverage is partial — several required skills are addressed, but at least one important skill is only weakly covered or does not clearly reach its required level.
    Score 2: limited coverage — multiple important skills are missing, incompletely progressed, or only implied rather than explicit.
    Score 1: one or more major in-progress skills are absent from desired outcomes or the path clearly fails to cover the required progression.
- scope_appropriateness: judge fit to the learner goal/background, not path length.
    Score 5: the plan covers a sensible amount of material for the learner's background and requested session count; each session has a realistic and achievable focus.
    Score 4: scope is generally realistic with only minor overreach or underreach in one session.
    Score 3: scope is borderline — several sessions are somewhat overloaded or somewhat shallow, making outcomes uneven but salvageable.
    Score 2: scope is frequently unrealistic — many sessions are clearly overpacked or underdeveloped for the learner level.
    Score 1: the plan is obviously overloaded or obviously trivial for the learner and requested session count.
- session_abstraction_quality: judge whether each abstract is specific, action-oriented, SOLO-appropriate for its desired outcomes, and consistent with the session flags.
    Score 5: each abstract clearly states what the session covers, what the learner will achieve, and the intended SOLO depth, while keeping any adaptation cues brief and consistent with the flags.
    Score 4: abstracts are mostly coverage-first and level-appropriate, with only occasional generic phrasing or slightly under/over-signaled depth.
    Score 3: mixed quality — some abstracts describe session substance and level well, but others are generic, repetitive, or vague about the intended depth.
    Score 2: many abstracts are vague, level-mismatched, repetitive, or primarily describe delivery style rather than session substance and learner outcome.
    Score 1: abstracts are nearly empty, generic, or consistently misstate what the learner will study and the depth they are expected to reach.
- fslsm_structural_alignment: judge the explicit structural flags against the learner's FSLSM dimensions, not generic personalization language or abstract phrasing.
    Score 5: the session-level structural fields match the learner's FSLSM profile well, or the learner is balanced and the structure is internally coherent.
    Score 4: structural choices largely align with FSLSM expectations, with at most one minor mismatch.
    Score 3: partial alignment — some FSLSM-driven fields are correct, but there are multiple mismatches or weak signals.
    Score 2: weak alignment — most structural choices conflict with the learner profile, though a few may align by chance.
    Score 1: the structural fields directly contradict the learner's FSLSM profile.
- solo_outcome_progression: judge whether outcome levels rise realistically, while treating the deterministic audit as the source of truth for illegal skips.
    Score 5: desired outcomes rise in a realistic, stepwise trajectory that matches the learner's starting level and the plan's pedagogical intent.
    Score 4: progression is mostly sensible with only one minor plateau or edge-case awkwardness.
    Score 3: progression is uneven — some steps make sense, but the overall trajectory has noticeable inconsistencies.
    Score 2: progression is largely implausible — repeated large jumps, unstable targeting, or weak developmental logic.
    Score 1: progression is irrational or regressive, even before considering deterministic audit caps.

Important: verify that your score and reason are consistent before writing the JSON.
A positive reason (for example "sessions are well-ordered", "all required skills are fully progressed", "FSLSM structure matches the learner") must map to a HIGH score (4 or 5).
A negative reason (for example "prerequisites are violated", "required skills are missing", "structure conflicts with FSLSM") must map to a LOW score (1 or 2).
"""


def _build_plan_audit(profile_body: dict, path_body: dict) -> dict:
    try:
        from modules.learning_plan_generator.agents.plan_feedback_simulator import build_deterministic_solo_audit

        return build_deterministic_solo_audit(profile_body, path_body)
    except Exception:
        return {
            "violation_count": 0,
            "coverage_gap_count": 0,
            "has_violations": False,
            "has_coverage_gaps": False,
            "coverage_gaps": [],
            "violations": [],
        }


def _abstract_flag_consistency(path_body: dict) -> dict:
    sessions = path_body.get("learning_path", []) if isinstance(path_body, dict) else []
    issues = []

    checkpoint_pattern = re.compile(r"\bcheckpoint\b|\bknowledge check\b|\bcheck-in\b")
    application_first_tokens = ("application", "example", "hands-on", "practice", "task", "build", "apply", "start with")
    theory_first_tokens = ("concept", "theory", "principle", "fundamentals", "model", "start with")
    visual_tokens = ("diagram", "chart", "visual", "module map", "walkthrough", "map")
    verbal_tokens = ("narrative", "written", "story", "analogy", "podcast", "audio", "discussion", "explanation")

    def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
        return any(token in text for token in tokens)

    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict):
            continue
        abstract = str(session.get("abstract", "") or "").lower()
        if not abstract:
            continue
        session_id = str(session.get("id") or f"Session {index}")
        mentions_checkpoint = bool(checkpoint_pattern.search(abstract))
        if session.get("has_checkpoint_challenges") and not mentions_checkpoint:
            issues.append({"session_id": session_id, "issue": "checkpoint_missing_from_abstract"})
        if not session.get("has_checkpoint_challenges") and mentions_checkpoint:
            issues.append({"session_id": session_id, "issue": "checkpoint_claim_without_flag"})
        thinking_minutes = int(session.get("thinking_time_buffer_minutes", 0) or 0)
        mentions_reflection = "reflection pause" in abstract or "reflection period" in abstract
        if thinking_minutes > 0 and not mentions_reflection:
            issues.append({"session_id": session_id, "issue": "reflection_missing_from_abstract"})
        if thinking_minutes == 0 and mentions_reflection:
            issues.append({"session_id": session_id, "issue": "reflection_claim_without_buffer"})
        sequence_hint = str(session.get("session_sequence_hint") or "").strip().lower()
        has_application_cue = _contains_any(abstract, application_first_tokens)
        has_theory_cue = _contains_any(abstract, theory_first_tokens)
        if sequence_hint == "application-first":
            if has_theory_cue and not has_application_cue:
                issues.append({"session_id": session_id, "issue": "application_first_contradicted"})
        if sequence_hint == "theory-first":
            if has_application_cue and not has_theory_cue:
                issues.append({"session_id": session_id, "issue": "theory_first_contradicted"})
        input_mode = str(session.get("input_mode_hint") or "").strip().lower()
        has_visual_cue = _contains_any(abstract, visual_tokens)
        has_verbal_cue = _contains_any(abstract, verbal_tokens)
        if input_mode == "visual" and has_verbal_cue and not has_visual_cue:
            issues.append({"session_id": session_id, "issue": "visual_mode_contradicted"})
        if input_mode == "verbal" and has_visual_cue and not has_verbal_cue:
            issues.append({"session_id": session_id, "issue": "verbal_mode_contradicted"})
    return {
        "issue_count": len(issues),
        "issues": issues,
    }


def _fslsm_structural_signals(profile_body: dict, path_body: dict) -> dict:
    sessions = path_body.get("learning_path", []) if isinstance(path_body, dict) else []
    dims = extract_fslsm_dimensions(profile_body) or {}
    issues = []

    def _dim(name: str) -> float:
        raw = dims.get(name, 0.0)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    processing = _dim("fslsm_processing")
    perception = _dim("fslsm_perception")
    input_pref = _dim("fslsm_input")
    understanding = _dim("fslsm_understanding")

    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict):
            continue
        session_id = str(session.get("id") or f"Session {index}")
        has_checkpoint = bool(session.get("has_checkpoint_challenges"))
        thinking_minutes = int(session.get("thinking_time_buffer_minutes", 0) or 0)
        sequence_hint = str(session.get("session_sequence_hint") or "").strip().lower()
        input_mode = str(session.get("input_mode_hint") or "").strip().lower()
        navigation_mode = str(session.get("navigation_mode") or "linear").strip().lower()

        if processing <= -0.3 and not has_checkpoint:
            issues.append({"session_id": session_id, "issue": "active_processing_missing_checkpoint"})
        if processing >= 0.3 and thinking_minutes <= 0:
            issues.append({"session_id": session_id, "issue": "reflective_processing_missing_buffer"})
        if perception <= -0.3 and sequence_hint != "application-first":
            issues.append({"session_id": session_id, "issue": "sensing_preference_missing_application_first"})
        if perception >= 0.3 and sequence_hint != "theory-first":
            issues.append({"session_id": session_id, "issue": "intuitive_preference_missing_theory_first"})
        if input_pref <= -0.3 and input_mode != "visual":
            issues.append({"session_id": session_id, "issue": "visual_preference_missing_visual_mode"})
        if input_pref >= 0.3 and input_mode != "verbal":
            issues.append({"session_id": session_id, "issue": "verbal_preference_missing_verbal_mode"})
        if understanding <= -0.3 and navigation_mode != "linear":
            issues.append({"session_id": session_id, "issue": "sequential_preference_missing_linear_navigation"})
        if understanding >= 0.3 and navigation_mode != "free":
            issues.append({"session_id": session_id, "issue": "global_preference_missing_free_navigation"})

    return {
        "issue_count": len(issues),
        "issues": issues,
        "dimensions": dims,
    }


_SOLO_LEVEL_ORDER = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
_SOLO_LEVEL_TOKENS = {
    "beginner": (
        "intro",
        "introduce",
        "introduction",
        "basic",
        "basics",
        "fundamental",
        "fundamentals",
        "core concept",
        "core concepts",
        "core idea",
        "guided",
        "step by step",
        "simple",
        "first",
        "recognize",
        "identify",
    ),
    "intermediate": (
        "connect",
        "connections",
        "combine",
        "apply",
        "application",
        "workflow",
        "structured task",
        "when to use",
        "why to use",
        "compare",
    ),
    "advanced": (
        "tradeoff",
        "tradeoffs",
        "extend",
        "optimize",
        "optimization",
        "architecture",
        "architect",
        "integrate",
        "integration",
        "realistic scenario",
        "refactor",
        "diagnose",
    ),
    "expert": (
        "generalize",
        "generalization",
        "transfer",
        "new context",
        "novel context",
        "critique",
        "strategic",
        "strategy",
        "govern",
        "justify",
    ),
}


def _dominant_target_level(session: dict) -> str | None:
    outcomes = session.get("desired_outcome_when_completed", [])
    if not isinstance(outcomes, list):
        return None
    dominant = None
    dominant_value = -1
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        level = str(outcome.get("level", "") or "").strip().lower()
        value = _SOLO_LEVEL_ORDER.get(level, -1)
        if value > dominant_value:
            dominant = level
            dominant_value = value
    return dominant


def _infer_abstract_level_signal(abstract: str) -> dict:
    lowered = abstract.lower()
    matches = {
        level: [token for token in tokens if token in lowered]
        for level, tokens in _SOLO_LEVEL_TOKENS.items()
    }
    matched_levels = [level for level, tokens in matches.items() if tokens]
    if not matched_levels:
        return {"inferred_level": None, "matched_tokens": {}, "matched_levels": []}
    inferred_level = max(matched_levels, key=lambda level: _SOLO_LEVEL_ORDER[level])
    return {
        "inferred_level": inferred_level,
        "matched_tokens": {level: tokens for level, tokens in matches.items() if tokens},
        "matched_levels": matched_levels,
    }


def _abstract_solo_signals(path_body: dict) -> dict:
    sessions = path_body.get("learning_path", []) if isinstance(path_body, dict) else []
    diagnostics = []
    issue_count = 0
    under_leveled = 0
    over_leveled = 0

    for index, session in enumerate(sessions, start=1):
        if not isinstance(session, dict):
            continue
        abstract = str(session.get("abstract", "") or "").strip()
        session_id = str(session.get("id") or f"Session {index}")
        target_level = _dominant_target_level(session)
        inferred = _infer_abstract_level_signal(abstract)
        inferred_level = inferred["inferred_level"]
        alignment = "unknown"
        issues = []
        if target_level and inferred_level:
            target_value = _SOLO_LEVEL_ORDER[target_level]
            inferred_value = _SOLO_LEVEL_ORDER[inferred_level]
            target_hits = len(inferred["matched_tokens"].get(target_level, []))
            inferred_hits = len(inferred["matched_tokens"].get(inferred_level, []))
            if inferred_value < target_value:
                if (target_value - inferred_value) == 1 and (target_hits > 0 or inferred_hits < 2):
                    alignment = "borderline"
                else:
                    alignment = "under_leveled"
                    issues.append("abstract_sounds_below_target_level")
                    under_leveled += 1
                    issue_count += 1
            elif inferred_value > target_value:
                if (inferred_value - target_value) == 1 and (target_hits > 0 or inferred_hits < 2):
                    alignment = "borderline"
                else:
                    alignment = "over_leveled"
                    issues.append("abstract_sounds_above_target_level")
                    over_leveled += 1
                    issue_count += 1
            else:
                alignment = "aligned"
        elif target_level:
            alignment = "unknown"

        diagnostics.append(
            {
                "session_id": session_id,
                "dominant_target_level": target_level,
                "abstract_level_signal": inferred_level,
                "abstract_level_alignment": alignment,
                "matched_level_tokens": inferred["matched_tokens"],
                "issues": issues,
            }
        )

    return {
        "session_count": len(diagnostics),
        "issue_count": issue_count,
        "under_leveled_count": under_leveled,
        "over_leveled_count": over_leveled,
        "sessions": diagnostics,
    }


def _apply_plan_guards(
    scores: dict,
    plan_audit: dict,
    abstract_flag_signals: dict,
    fslsm_structural_signals: dict,
) -> dict:
    adjusted = json.loads(json.dumps(scores))

    def _cap(metric: str, cap: int, note: str) -> None:
        bucket = adjusted.get(metric)
        if not isinstance(bucket, dict):
            return
        current = bucket.get("score")
        if isinstance(current, int) and current > cap:
            bucket["score"] = cap
            reason = str(bucket.get("reason", "")).strip()
            bucket["reason"] = f"{reason} {note}".strip()

    if int(plan_audit.get("violation_count", 0) or 0) > 0:
        _cap("pedagogical_sequencing", 2, "Capped by deterministic SOLO audit: level-skipping transition detected.")
        _cap("solo_outcome_progression", 2, "Capped by deterministic SOLO audit: outcome progression is not legally stepwise.")
    coverage_gap_count = int(plan_audit.get("coverage_gap_count", 0) or 0)
    coverage_gaps = plan_audit.get("coverage_gaps", [])
    has_major_missing_skill = False
    if isinstance(coverage_gaps, list):
        for gap in coverage_gaps:
            if not isinstance(gap, dict):
                continue
            current_level = str(gap.get("current_level", "") or "").strip().lower()
            reached_level = str(gap.get("reached_level", "") or "").strip().lower()
            missing_levels = gap.get("missing_levels", [])
            if reached_level == current_level or (isinstance(missing_levels, list) and len(missing_levels) >= 2):
                has_major_missing_skill = True
                break
    if has_major_missing_skill:
        _cap("skill_coverage", 1, "Capped by deterministic SOLO audit: one or more major skills never progressed enough to close the gap.")
    elif coverage_gap_count > 1:
        _cap("skill_coverage", 2, "Capped by deterministic SOLO audit: multiple progression coverage gaps remain.")
    elif coverage_gap_count == 1:
        _cap("skill_coverage", 3, "Capped by deterministic SOLO audit: one progression coverage gap remains.")
    if int(abstract_flag_signals.get("issue_count", 0) or 0) > 0:
        _cap("session_abstraction_quality", 3, "Capped by flag/abstract consistency audit.")
    if int(fslsm_structural_signals.get("issue_count", 0) or 0) > 0:
        _cap("fslsm_structural_alignment", 3, "Capped by FSLSM structural flag audit.")
    return adjusted


def _base_payload(extra: dict) -> dict:
    payload = dict(extra)
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME
    return payload


def _api_learner_info(scenario: dict) -> str:
    return scenario.get("learner_information_enhanced", scenario["learner_information"])


def _unwrap_profile_body(profile_body: dict) -> dict:
    if not isinstance(profile_body, dict):
        return {}
    inner = profile_body.get("learner_profile")
    return inner if isinstance(inner, dict) else profile_body


def _count_skill_gaps(skill_gap_body: dict) -> int:
    raw = skill_gap_body.get("skill_gaps", [])
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, str):
        try:
            return len(json.loads(raw))
        except Exception:
            try:
                return len(ast.literal_eval(raw))
            except Exception:
                return 0
    return 0


def _is_ok_timing_entry(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("error"):
        return False
    if entry.get("status_code", 200) >= 400:
        return False
    return isinstance(entry.get("body"), dict)


def _evaluate_plan_outputs(scenario: dict, sg_body: dict, profile_body: dict, path_body: dict) -> dict:
    skill_gap_count = _count_skill_gaps(sg_body)
    if skill_gap_count == 0:
        return {
            "scenario_id": scenario["id"],
            "version": VERSION_KEY,
            "not_applicable": True,
            "not_applicable_reason": "zero_skill_gaps",
            "pipeline_outputs": {
                "skill_gap_count": 0,
                "learning_path_session_count": len(path_body.get("learning_path", [])) if isinstance(path_body, dict) else 0,
            },
        }

    plan_audit = _build_plan_audit(profile_body, path_body)
    flag_signals = _abstract_flag_consistency(path_body)
    fslsm_structural_signals = _fslsm_structural_signals(profile_body, path_body)
    abstract_solo_signals = _abstract_solo_signals(path_body)
    fslsm = extract_fslsm_dimensions(profile_body)
    user_prompt = SHARED_JUDGE_USER.format(
        learner_information=scenario["learner_information"],
        learning_goal=scenario["learning_goal"],
        skill_gaps=extract_skill_gaps_summary(sg_body),
        session_count=DEFAULT_SESSION_COUNT,
        learning_path=extract_learning_path_summary(path_body),
        fslsm=json.dumps(fslsm, indent=2) if fslsm else "N/A",
        plan_audit=json.dumps(plan_audit, indent=2),
        fslsm_structural_signals=json.dumps(fslsm_structural_signals, indent=2),
        flag_signals=json.dumps(flag_signals, indent=2),
        abstract_solo_signals=json.dumps(abstract_solo_signals, indent=2),
    )
    scores = _apply_plan_guards(
        judge(SHARED_JUDGE_SYSTEM, user_prompt),
        plan_audit,
        flag_signals,
        fslsm_structural_signals,
    )
    return {
        "scenario_id": scenario["id"],
        "version": VERSION_KEY,
        "pipeline_outputs": {
            "skill_gaps": json.loads(extract_skill_gaps_summary(sg_body)),
            "skill_gap_count": skill_gap_count,
            "learning_path_session_count": len(path_body.get("learning_path", [])),
            "plan_audit": plan_audit,
            "fslsm_structural_signals": fslsm_structural_signals,
            "fslsm_flag_signals": flag_signals,
            "abstract_solo_signals": abstract_solo_signals,
        },
        "scores": scores,
    }


def evaluate_scenario(scenario: dict, base_url: str, headers: dict[str, str]) -> dict:
    with httpx.Client(timeout=120.0) as client:
        try:
            sg_resp = client.post(
                f"{base_url}/identify-skill-gap-with-info",
                json=_base_payload(
                    {
                        "learning_goal": scenario["learning_goal"],
                        "learner_information": _api_learner_info(scenario),
                    }
                ),
                headers=headers,
            )
            sg_resp.raise_for_status()
            sg_body = sg_resp.json()

            profile_resp = client.post(
                f"{base_url}/create-learner-profile-with-info",
                json=_base_payload(
                    {
                        "learning_goal": scenario["learning_goal"],
                        "learner_information": _api_learner_info(scenario),
                        "skill_gaps": json.dumps(sg_body.get("skill_gaps", [])),
                    }
                ),
                headers=headers,
            )
            profile_resp.raise_for_status()
            profile_body = _unwrap_profile_body(profile_resp.json())

            path_resp = client.post(
                f"{base_url}/schedule-learning-path",
                json=_base_payload(
                    {
                        "learner_profile": json.dumps(profile_body),
                        "session_count": DEFAULT_SESSION_COUNT,
                    }
                ),
                headers=headers,
            )
            path_resp.raise_for_status()
            path_body = path_resp.json()
        except Exception as exc:
            return {"scenario_id": scenario["id"], "version": VERSION_KEY, "error": str(exc)}
    return _evaluate_plan_outputs(scenario, sg_body, profile_body, path_body)


def run_eval_plan(
    scenarios: list[dict],
    prefetched_runs: dict | None = None,
    *,
    base_url: str = BETA_BASE_URL,
) -> dict:
    headers = bootstrap_auth_headers(base_url)
    prefetched_index = {}
    for run in (prefetched_runs or {}).get(VERSION_KEY, {}).get("raw_runs", []):
        sid = run.get("scenario_id")
        if sid:
            prefetched_index[sid] = run.get("timings", {})

    results = []
    print(f"\n=== Learning Plan Eval: {VERSION_LABEL} ===")
    for scenario in scenarios:
        sid = scenario["id"]
        timings = prefetched_index.get(sid, {})
        sg_t = timings.get("identify_skill_gap")
        profile_t = timings.get("create_learner_profile")
        path_t = timings.get("schedule_learning_path")
        if _is_ok_timing_entry(sg_t) and _is_ok_timing_entry(profile_t) and _is_ok_timing_entry(path_t):
            print(f"  [{VERSION_KEY}] {sid} — judging (using prefetched onboarding outputs)...")
            result = _evaluate_plan_outputs(
                scenario,
                sg_t["body"],
                _unwrap_profile_body(profile_t["body"]),
                path_t["body"],
            )
            result["used_prefetched_api_output"] = True
        else:
            print(f"  [{VERSION_KEY}] {sid} — running onboarding pipeline...")
            result = evaluate_scenario(scenario, base_url, headers)
        results.append(result)
    return {VERSION_KEY: results}


def summarise(all_results: dict) -> dict:
    dims = [
        "pedagogical_sequencing",
        "skill_coverage",
        "scope_appropriateness",
        "session_abstraction_quality",
        "fslsm_structural_alignment",
        "solo_outcome_progression",
    ]
    results = all_results.get(VERSION_KEY, [])
    scores_list = [result.get("scores", {}) for result in results if "scores" in result]
    version_summary = {dim: average_score(scores_list, dim) for dim in dims}
    version_summary["scenario_count"] = len(results)
    version_summary["scored_scenario_count"] = len(scores_list)
    version_summary["not_applicable_zero_gap_count"] = sum(
        1 for result in results if result.get("not_applicable_reason") == "zero_skill_gaps"
    )
    version_summary["error_count"] = sum(1 for result in results if "error" in result)
    plan_audits = [result.get("pipeline_outputs", {}).get("plan_audit", {}) for result in results if "scores" in result]
    flag_signals = [result.get("pipeline_outputs", {}).get("fslsm_flag_signals", {}) for result in results if "scores" in result]
    abstract_solo_signals = [result.get("pipeline_outputs", {}).get("abstract_solo_signals", {}) for result in results if "scores" in result]
    version_summary["deterministic_plan_audit"] = {
        "total_violation_count": sum(int(item.get("violation_count", 0) or 0) for item in plan_audits),
        "total_coverage_gap_count": sum(int(item.get("coverage_gap_count", 0) or 0) for item in plan_audits),
        "scenarios_with_violations": sum(1 for item in plan_audits if item.get("has_violations")),
        "scenarios_with_coverage_gaps": sum(1 for item in plan_audits if item.get("has_coverage_gaps")),
        "scenarios_with_flag_inconsistencies": sum(1 for item in flag_signals if int(item.get("issue_count", 0) or 0) > 0),
    }
    version_summary["abstract_solo_signals"] = {
        "scenarios_with_level_signal_issues": sum(1 for item in abstract_solo_signals if int(item.get("issue_count", 0) or 0) > 0),
        "total_under_leveled_count": sum(int(item.get("under_leveled_count", 0) or 0) for item in abstract_solo_signals),
        "total_over_leveled_count": sum(int(item.get("over_leveled_count", 0) or 0) for item in abstract_solo_signals),
    }
    version_summary["category_metadata"] = get_category_metadata("plan")
    version_summary["metric_metadata"] = get_metric_metadata("plan", dims)
    return {VERSION_KEY: version_summary}


if __name__ == "__main__":
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)

    all_results = run_eval_plan(dataset["scenarios"])
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "plan_results.json")
    with open(out_path, "w") as file:
        json.dump({"results": all_results, "summary": summary}, file, indent=2)

    print("\n=== Learning Plan Evaluation Summary ===")
    for dim, score in summary[VERSION_KEY].items():
        print(f"  {dim}: {score}")
    print(f"\nFull results saved to {out_path}")
