"""
Skill Gap Evaluation — LLM-as-a-Judge via LangSmith

Runs /refine-learning-goal then /identify-skill-gap-with-info on both
GenMentor and the enhanced system for each of the 9 shared scenarios,
then judges the output on shared + enhanced-only dimensions.

Usage:
    python -m evals.eval_skill_gap
"""

import json
import os
import httpx

from evals.config import VERSIONS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, DATASETS_DIR, RESULTS_DIR
from evals.utils.llm_judge import judge, average_score
from evals.utils.schema_adapter import (
    extract_skill_gaps_summary,
    extract_skill_requirements_summary,
    extract_refined_goal,
)

SHARED_JUDGE_SYSTEM = """\
You are an expert evaluator for a personalized learning system.
You will be given the output of a Skill Gap Identification pipeline and asked to
rate it on several dimensions using a 1-5 scale.
Respond ONLY with valid JSON matching the schema described in the user prompt.
Do not include explanations outside the JSON object."""

SHARED_JUDGE_USER = """\
Learning Goal: {learning_goal}
Learner Background: {learner_information}
Refined Goal: {refined_goal}
Identified Skill Requirements:
{skill_requirements}
Identified Skill Gaps:
{skill_gaps}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "completeness": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "gap_calibration": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "goal_refinement_quality": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "confidence_validity": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring rubric:
- completeness: 1=major relevant skills missing, 5=all key skills present
- gap_calibration: 1=proficiency levels inconsistent with background, 5=well-calibrated
- goal_refinement_quality: 1=vague/off-topic refinement, 5=specific and actionable
- confidence_validity: 1=confidence scores seem arbitrary, 5=correlated with info availability"""

ENHANCED_JUDGE_USER_EXTENSION = """\

Additionally evaluate these enhanced-only dimensions:
{{
  "expert_calibration": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_level_accuracy": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

SOLO rubric:
- Prestructural / unlearned: no relevant knowledge
- Unistructural (beginner): one relevant aspect known
- Multistructural (intermediate): several aspects known but not integrated
- Relational (advanced): aspects integrated into a coherent understanding
- Extended Abstract (expert): can generalise and innovate beyond the domain

- expert_calibration: 1=expert never used even when background clearly warrants it, 5=expert correctly applied
- solo_level_accuracy: 1=current SOLO levels inconsistent with stated background, 5=precisely SOLO-grounded

Respond with ONLY a single merged JSON object containing all 6 dimensions."""


def _api_learner_info(scenario: dict, version_key: str) -> str:
    """
    Return the learner_information string that matches how each system's
    real onboarding flow constructs it:
      - genmentor:  occupation_label + background_text  (onboarding.py:149)
      - enhanced:   persona_prefix (with FSLSM vector) + background_text  (onboarding.py:245)
    The plain 'learner_information' key (background text only) is reserved for
    judge prompts so the evaluator sees neutral context without system-specific prefixes.
    """
    key = f"learner_information_{version_key}"
    return scenario.get(key, scenario["learner_information"])


def call_refine_goal(base_url: str, learning_goal: str, learner_information: str) -> str:
    payload = {
        "learning_goal": learning_goal,
        "learner_information": learner_information,
    }
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME

    with httpx.Client() as client:
        resp = client.post(f"{base_url}/refine-learning-goal", json=payload, timeout=60.0)
        resp.raise_for_status()
        body = resp.json()
        return body.get("refined_goal") or body.get("learning_goal") or learning_goal


def call_skill_gap(base_url: str, learning_goal: str, learner_information: str) -> dict:
    payload = {
        "learning_goal": learning_goal,
        "learner_information": learner_information,
    }
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME

    with httpx.Client() as client:
        resp = client.post(f"{base_url}/identify-skill-gap-with-info", json=payload, timeout=90.0)
        resp.raise_for_status()
        return resp.json()


def evaluate_scenario(scenario: dict, version_key: str, version_cfg: dict) -> dict:
    sid = scenario["id"]
    goal = scenario["learning_goal"]
    info = scenario["learner_information"]           # plain text — for judge context only
    api_info = _api_learner_info(scenario, version_key)  # prefixed — for API calls
    base_url = version_cfg["base_url"]
    is_enhanced = version_cfg["has_solo"]

    print(f"  [{version_key}] {sid} — calling /identify-skill-gap-with-info...")
    try:
        sg_body = call_skill_gap(base_url, goal, api_info)
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"scenario_id": sid, "version": version_key, "error": str(e)}

    refined_goal = extract_refined_goal(sg_body)
    skill_reqs = extract_skill_requirements_summary(sg_body)
    skill_gaps = extract_skill_gaps_summary(sg_body)

    user_prompt = SHARED_JUDGE_USER.format(
        learning_goal=goal,
        learner_information=info,
        refined_goal=refined_goal,
        skill_requirements=skill_reqs,
        skill_gaps=skill_gaps,
    )
    if is_enhanced:
        user_prompt += "\n\n" + ENHANCED_JUDGE_USER_EXTENSION

    print(f"  [{version_key}] {sid} — judging...")
    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)

    return {
        "scenario_id": sid,
        "version": version_key,
        "raw_output": {
            "refined_goal": refined_goal,
            "skill_requirements": json.loads(skill_reqs),
            "skill_gaps": json.loads(skill_gaps),
        },
        "scores": scores,
    }


def run_eval_skill_gap(scenarios: list[dict]) -> dict:
    all_results = {}

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== Skill Gap Eval: {version_cfg['label']} ===")
        version_results = []
        for scenario in scenarios:
            result = evaluate_scenario(scenario, version_key, version_cfg)
            version_results.append(result)
        all_results[version_key] = version_results

    return all_results


def summarise(all_results: dict) -> dict:
    shared_dims = ["completeness", "gap_calibration", "goal_refinement_quality", "confidence_validity"]
    enhanced_dims = ["expert_calibration", "solo_level_accuracy"]
    summary = {}

    for version_key, results in all_results.items():
        scores_list = [r.get("scores", {}) for r in results if "scores" in r]
        version_summary = {}
        for dim in shared_dims:
            version_summary[dim] = average_score(scores_list, dim)
        if VERSIONS[version_key]["has_solo"]:
            for dim in enhanced_dims:
                version_summary[dim] = average_score(scores_list, dim)
        summary[version_key] = version_summary

    return summary


if __name__ == "__main__":
    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)
    scenarios = dataset["scenarios"]

    all_results = run_eval_skill_gap(scenarios)
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "skill_gap_results.json")
    with open(out_path, "w") as f:
        json.dump({"results": all_results, "summary": summary}, f, indent=2)

    print("\n=== Skill Gap Evaluation Summary ===")
    for version_key, scores in summary.items():
        print(f"\n{VERSIONS[version_key]['label']}:")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")

    print(f"\nFull results saved to {out_path}")
