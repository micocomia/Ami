"""
Learning Plan Evaluation — LLM-as-a-Judge

For each scenario, runs the full onboarding pipeline on both versions:
  /refine-learning-goal → /identify-skill-gap-with-info
  → /create-learner-profile-with-info → /schedule-learning-path

Then judges the generated learning path on shared and enhanced-only dimensions.

Usage:
    python -m evals.eval_plan
"""

import json
import os
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

Scoring rubric:
- pedagogical_sequencing: 1=random order ignoring prerequisites, 5=ideal prerequisite order
- skill_coverage: 1=many skill gaps unaddressed, 5=every gap maps to at least one session
- scope_appropriateness: 1=wildly too shallow or too deep for N sessions, 5=realistic depth
- session_abstraction_quality: 1=session titles/abstracts vague/redundant, 5=distinct and meaningful"""

ENHANCED_JUDGE_USER_EXTENSION = """\

Also evaluate these enhanced-only dimensions given the learner's FSLSM profile:
FSLSM Dimensions: {fslsm_dimensions}
(Scale: -1.0 to +1.0; processing: -1=active, +1=reflective; perception: -1=sensing, +1=intuitive;
 input: -1=visual, +1=verbal; understanding: -1=sequential, +1=global)

{{
  "fslsm_structural_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_outcome_progression": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

FSLSM structural alignment guide (check session-level fields):
- Active learner (processing ≤ -0.5): should have has_checkpoint_challenges=true
- Reflective learner (processing ≥ 0.5): should have thinking_time_buffer_minutes > 0
- Sequential learner (understanding ≤ -0.5): navigation_mode should be "linear"
- Global learner (understanding ≥ 0.5): navigation_mode should be "free"

SOLO outcome progression: desired_outcome_when_completed proficiency levels should not skip
levels (beginner → intermediate → advanced → expert), or justify if they do.

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
        profile_body = profile_resp.json()

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
            "learning_path_session_count": len(path_body.get("learning_path", [])),
        },
        "scores": scores,
    }


def run_eval_plan(scenarios: list[dict]) -> dict:
    all_results = {}
    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== Learning Plan Eval: {version_cfg['label']} ===")
        version_results = []
        for scenario in scenarios:
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
