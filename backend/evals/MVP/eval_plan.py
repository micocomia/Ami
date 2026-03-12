"""
Learning Plan Evaluation — LLM-as-a-Judge

For each scenario, runs the full onboarding pipeline on both versions:
  /identify-skill-gap-with-info
  → /create-learner-profile-with-info → /schedule-learning-path

Then judges the generated learning path on shared and enhanced-only dimensions.

Usage:
    python -m evals.eval_plan
"""

import json
import os
import ast
import httpx

from evals.config import VERSIONS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, DATASETS_DIR, RESULTS_DIR, DEFAULT_SESSION_COUNT
from evals.utils.llm_judge import judge, average_score
from evals.utils.schema_adapter import (
    extract_skill_gaps_summary,
    extract_learning_path_summary,
    extract_fslsm_dimensions,
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
Generated Learning Path:
{learning_path}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "pedagogical_sequencing": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "skill_coverage": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "scope_appropriateness": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "session_abstraction_quality": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring rubric — higher is always better:
- pedagogical_sequencing: Are sessions ordered so that foundational skills are taught before dependent ones?
    Score 5: sessions build on each other correctly — prerequisites appear before the skills that depend on them, and no session requires knowledge not yet covered.
    Score 4: sequencing is mostly correct with only minor ordering issues that do not materially block learning progression.
    Score 3: sequencing is mixed — some prerequisites are in place, but multiple sessions require concepts introduced too late or inconsistently.
    Score 2: sequencing is poor — prerequisite violations are frequent and likely to confuse most learners, though a few local sequences still make sense.
    Score 1: sessions are ordered with no regard for prerequisites — advanced topics appear before foundational ones are established.
    Note: if the skill gaps are largely independent of each other, any coherent grouping is acceptable and should score 4 or 5.
- skill_coverage: Does the learning path address all the listed skill gaps, directly or thematically?
    Score 5: every skill gap in the list is covered in at least one session, either by exact topic or by a closely related session focus.
    Score 4: almost all skill gaps are covered; only one minor gap is weakly addressed or implied rather than explicit.
    Score 3: partial coverage; several skill gaps are addressed, but at least one important gap is only superficially covered or ambiguous.
    Score 2: limited coverage; multiple important gaps are missing, with only a subset of the required areas addressed.
    Score 1: one or more major skill gaps from the list are entirely absent from the learning path with no related session covering them.
- scope_appropriateness: Is the depth and breadth of the plan realistic given the session count and learner background?
    Score 5: the plan covers a sensible amount of material — each session has a clear, achievable focus that suits the given number of sessions and the learner's starting level.
    Score 4: scope is generally realistic with minor overreach or underreach in one session, but still feasible overall.
    Score 3: scope is borderline — several sessions are either a bit overloaded or a bit shallow, making outcomes uneven but potentially salvageable.
    Score 2: scope is frequently unrealistic — many sessions are clearly overpacked or underdeveloped for the learner level and available session count.
    Score 1: the plan is obviously overloaded (far too many distinct topics crammed into too few sessions) or obviously trivial (sessions contain near-empty or redundant content) for the requested session count.
- session_abstraction_quality: Are session titles and descriptions distinct, specific, and informative?
    Score 5: each session has a unique, clearly scoped focus; titles and descriptions communicate what the learner will concretely do or learn.
    Score 4: sessions are mostly distinct and specific, with only occasional generic phrasing or slight overlap between neighboring sessions.
    Score 3: mixed specificity — some sessions are concrete, but others are generic, repetitive, or unclear about expected outcomes.
    Score 2: many sessions are vague or repetitive, with limited actionable detail about what the learner will do.
    Score 1: sessions are vaguely titled (e.g., "Introduction", "More learning"), nearly identical to each other, or their descriptions fail to convey any concrete learning objective.

Important: verify that your score and reason are consistent before writing the JSON.
A positive reason (e.g., "sessions are well-ordered", "all gaps covered") must map to a HIGH score (4 or 5).
A negative reason (e.g., "prerequisite ordering violated", "major gaps missing") must map to a LOW score (1 or 2)."""

ENHANCED_JUDGE_USER_EXTENSION = """\

Also evaluate these two enhanced-only dimensions and merge them into the same JSON object:
FSLSM Dimensions: {fslsm_dimensions}
(Scale: -1.0 to +1.0; processing: -1=active, +1=reflective; perception: -1=sensing, +1=intuitive;
 input: -1=visual, +1=verbal; understanding: -1=sequential, +1=global)

{{
  "fslsm_structural_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_outcome_progression": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

FSLSM structural alignment — check the session-level fields against the expected values:
- Active learner (processing ≤ -0.5): sessions should have has_checkpoint_challenges=true
- Reflective learner (processing ≥ 0.5): sessions should have thinking_time_buffer_minutes > 0
- Sequential learner (understanding ≤ -0.5): navigation_mode should be "linear"
- Global learner (understanding ≥ 0.5): navigation_mode should be "free"
- Balanced learner (all dimensions near 0.0): any consistent structural choice is acceptable

- fslsm_structural_alignment:
    Score 5: the session-level structural fields match what the FSLSM profile calls for, or the learner is balanced and the fields are internally consistent.
    Score 4: structural fields largely align with FSLSM expectations, with at most one minor mismatch that does not undermine the overall fit.
    Score 3: partial alignment — some FSLSM-driven fields are correct, but there are multiple mismatches or inconsistencies.
    Score 2: weak alignment — most structural choices conflict with the FSLSM profile, though a small subset may still match by chance.
    Score 1: the structural fields directly contradict the FSLSM profile (e.g., an active learner has no checkpoint challenges, or a sequential learner is assigned free navigation).

SOLO outcome progression — do the desired_outcome_when_completed proficiency levels advance sensibly?
- solo_outcome_progression:
    Score 5: proficiency levels step up gradually across sessions (e.g., unlearned → beginner → intermediate), matching the learner's starting level with no unjustified skips.
    Score 4: progression is mostly sensible with one minor jump or plateau, but the overall trajectory remains realistic.
    Score 3: progression is uneven — includes a few abrupt jumps or inconsistencies, yet still shows a recognizable upward learning direction.
    Score 2: progression is largely implausible — repeated large jumps, regressions, or unstable level targeting across sessions.
    Score 1: proficiency levels jump irrationally (e.g., unlearned directly to expert) or regress (a later session targets a lower level than an earlier one) with no clear justification.

Respond with ONLY a single merged JSON object containing all 6 dimensions."""


def _base_payload(extra: dict) -> dict:
    payload = dict(extra)
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME
    return payload


def _api_learner_info(scenario: dict, version_key: str) -> str:
    """Return the version-specific prefixed learner_information for API calls."""
    key = f"learner_information_{version_key}"
    return scenario.get(key, scenario["learner_information"])


def _unwrap_profile_body(profile_body: dict) -> dict:
    """
    Normalise profile response shape across systems:
      - {"learner_profile": {...}} -> {...}
      - {...} -> {...}
    """
    if not isinstance(profile_body, dict):
        return {}
    inner = profile_body.get("learner_profile")
    if isinstance(inner, dict):
        return inner
    return profile_body


def _count_skill_gaps(sg_body: dict) -> int:
    """Best-effort count of identified skill gaps from API response body."""
    if not isinstance(sg_body, dict):
        return 0
    raw = sg_body.get("skill_gaps", [])
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return len(parsed)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return len(parsed)
        except Exception:
            pass
    return 0


def run_onboarding_pipeline(base_url: str, learning_goal: str, learner_information: str) -> dict:
    """
    Run the full onboarding pipeline and return all intermediate outputs.
    Returns dict with keys: skill_gaps_body, profile_body, path_body
    """
    with httpx.Client(timeout=120.0) as client:
        # 1. Skill gap identification (implicitly refines goal)
        sg_resp = client.post(
            f"{base_url}/identify-skill-gap-with-info",
            json=_base_payload({"learning_goal": learning_goal, "learner_information": learner_information}),
        )
        sg_resp.raise_for_status()
        sg_body = sg_resp.json()

        skill_gaps_str = json.dumps(sg_body.get("skill_gaps", []))

        # 2. Profile creation
        profile_resp = client.post(
            f"{base_url}/create-learner-profile-with-info",
            json=_base_payload({
                "learning_goal": learning_goal,
                "learner_information": learner_information,
                "skill_gaps": skill_gaps_str,
            }),
        )
        profile_resp.raise_for_status()
        profile_body = _unwrap_profile_body(profile_resp.json())

        # 3. Learning path scheduling
        path_resp = client.post(
            f"{base_url}/schedule-learning-path",
            json=_base_payload({
                "learner_profile": json.dumps(profile_body),
                "session_count": DEFAULT_SESSION_COUNT,
            }),
        )
        path_resp.raise_for_status()
        path_body = path_resp.json()

    return {
        "skill_gaps_body": sg_body,
        "profile_body": profile_body,
        "path_body": path_body,
    }


def _is_ok_timing_entry(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("error"):
        return False
    if entry.get("status_code", 200) >= 400:
        return False
    return isinstance(entry.get("body"), dict)


def evaluate_scenario(scenario: dict, version_key: str, version_cfg: dict) -> dict:
    sid = scenario["id"]
    goal = scenario["learning_goal"]
    info = scenario["learner_information"]           # plain text — for judge context only
    api_info = _api_learner_info(scenario, version_key)  # prefixed — for API calls
    base_url = version_cfg["base_url"]
    is_enhanced = version_cfg["has_fslsm"]

    print(f"  [{version_key}] {sid} — running onboarding pipeline...")
    try:
        pipeline_out = run_onboarding_pipeline(base_url, goal, api_info)
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"scenario_id": sid, "version": version_key, "error": str(e)}

    sg_body = pipeline_out["skill_gaps_body"]
    profile_body = pipeline_out["profile_body"]
    path_body = pipeline_out["path_body"]
    skill_gap_count = _count_skill_gaps(sg_body)

    if skill_gap_count == 0:
        return {
            "scenario_id": sid,
            "version": version_key,
            "not_applicable": True,
            "not_applicable_reason": "zero_skill_gaps",
            "pipeline_outputs": {
                "skill_gap_count": 0,
                "learning_path_session_count": len(path_body.get("learning_path", [])) if isinstance(path_body, dict) else 0,
            },
        }

    skill_gaps = extract_skill_gaps_summary(sg_body)
    learning_path = extract_learning_path_summary(path_body)

    user_prompt = SHARED_JUDGE_USER.format(
        learner_information=info,
        learning_goal=goal,
        skill_gaps=skill_gaps,
        session_count=DEFAULT_SESSION_COUNT,
        learning_path=learning_path,
    )

    if is_enhanced:
        fslsm = extract_fslsm_dimensions(profile_body)
        user_prompt += "\n\n" + ENHANCED_JUDGE_USER_EXTENSION.format(
            fslsm_dimensions=json.dumps(fslsm, indent=2) if fslsm else "N/A"
        )

    print(f"  [{version_key}] {sid} — judging...")
    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)

    return {
        "scenario_id": sid,
        "version": version_key,
        "pipeline_outputs": {
            "skill_gaps": json.loads(skill_gaps),
            "skill_gap_count": skill_gap_count,
            "learning_path_session_count": len(path_body.get("learning_path", [])),
        },
        "scores": scores,
    }


def run_eval_plan(scenarios: list[dict], prefetched_runs: dict | None = None) -> dict:
    all_results = {}

    # Optional index from API perf results:
    # prefetched_runs[version_key]["raw_runs"] = [{"scenario_id": ..., "timings": {...}}, ...]
    prefetched_index: dict[str, dict[str, dict]] = {}
    if prefetched_runs:
        for v_key, v_data in prefetched_runs.items():
            scenario_map = {}
            for run in (v_data or {}).get("raw_runs", []):
                sid = run.get("scenario_id")
                if sid:
                    scenario_map[sid] = run.get("timings", {})
            prefetched_index[v_key] = scenario_map

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== Learning Plan Eval: {version_cfg['label']} ===")
        version_results = []
        for scenario in scenarios:
            sid = scenario["id"]
            timings = prefetched_index.get(version_key, {}).get(sid, {})
            sg_t = timings.get("identify_skill_gap")
            profile_t = timings.get("create_learner_profile")
            path_t = timings.get("schedule_learning_path")

            if _is_ok_timing_entry(sg_t) and _is_ok_timing_entry(profile_t) and _is_ok_timing_entry(path_t):
                sg_body = sg_t["body"]
                profile_body = _unwrap_profile_body(profile_t["body"])
                path_body = path_t["body"]
                skill_gap_count = _count_skill_gaps(sg_body)

                if skill_gap_count == 0:
                    result = {
                        "scenario_id": sid,
                        "version": version_key,
                        "not_applicable": True,
                        "not_applicable_reason": "zero_skill_gaps",
                        "pipeline_outputs": {
                            "skill_gap_count": 0,
                            "learning_path_session_count": len(path_body.get("learning_path", [])),
                        },
                        "used_prefetched_api_output": True,
                    }
                    version_results.append(result)
                    continue

                goal = scenario["learning_goal"]
                info = scenario["learner_information"]  # plain text — for judge context only
                is_enhanced = version_cfg["has_fslsm"]

                skill_gaps = extract_skill_gaps_summary(sg_body)
                learning_path = extract_learning_path_summary(path_body)

                user_prompt = SHARED_JUDGE_USER.format(
                    learner_information=info,
                    learning_goal=goal,
                    skill_gaps=skill_gaps,
                    session_count=DEFAULT_SESSION_COUNT,
                    learning_path=learning_path,
                )
                if is_enhanced:
                    fslsm = extract_fslsm_dimensions(profile_body)
                    user_prompt += "\n\n" + ENHANCED_JUDGE_USER_EXTENSION.format(
                        fslsm_dimensions=json.dumps(fslsm, indent=2) if fslsm else "N/A"
                    )

                print(f"  [{version_key}] {sid} — judging (using prefetched onboarding outputs)...")
                scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)
                result = {
                    "scenario_id": sid,
                    "version": version_key,
                    "pipeline_outputs": {
                        "skill_gaps": json.loads(skill_gaps),
                        "skill_gap_count": skill_gap_count,
                        "learning_path_session_count": len(path_body.get("learning_path", [])),
                    },
                    "scores": scores,
                    "used_prefetched_api_output": True,
                }
            else:
                result = evaluate_scenario(scenario, version_key, version_cfg)
            version_results.append(result)
        all_results[version_key] = version_results
    return all_results


def summarise(all_results: dict) -> dict:
    shared_dims = ["pedagogical_sequencing", "skill_coverage", "scope_appropriateness", "session_abstraction_quality"]
    enhanced_dims = ["fslsm_structural_alignment", "solo_outcome_progression"]
    summary = {}
    for version_key, results in all_results.items():
        scores_list = [r.get("scores", {}) for r in results if "scores" in r]
        version_summary = {}
        for dim in shared_dims:
            version_summary[dim] = average_score(scores_list, dim)
        if VERSIONS[version_key]["has_fslsm"]:
            for dim in enhanced_dims:
                version_summary[dim] = average_score(scores_list, dim)
        version_summary["scenario_count"] = len(results)
        version_summary["scored_scenario_count"] = len(scores_list)
        version_summary["not_applicable_zero_gap_count"] = sum(
            1 for r in results if r.get("not_applicable_reason") == "zero_skill_gaps"
        )
        version_summary["error_count"] = sum(1 for r in results if "error" in r)
        summary[version_key] = version_summary
    return summary


if __name__ == "__main__":
    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)
    scenarios = dataset["scenarios"]

    all_results = run_eval_plan(scenarios)
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "plan_results.json")
    with open(out_path, "w") as f:
        json.dump({"results": all_results, "summary": summary}, f, indent=2)

    print("\n=== Learning Plan Evaluation Summary ===")
    for version_key, scores in summary.items():
        print(f"\n{VERSIONS[version_key]['label']}:")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")

    print(f"\nFull results saved to {out_path}")
