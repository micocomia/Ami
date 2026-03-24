"""Skill gap evaluation for the current backend."""

import json
import os

import httpx

from evals.Beta.auth import bootstrap_auth_headers
from evals.Beta.config import (
    BETA_BASE_URL,
    DATASETS_DIR,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    RESULTS_DIR,
    VERSION_KEY,
    VERSION_LABEL,
)
from evals.Beta.metric_metadata import get_category_metadata, get_metric_metadata
from evals.Beta.utils.llm_judge import average_score, judge
from evals.Beta.utils.schema_adapter import (
    extract_goal_assessment,
    extract_goal_context,
    extract_refined_goal,
    extract_retrieved_sources,
    extract_skill_gaps_summary,
    extract_skill_requirements_summary,
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
Goal Assessment:
{goal_assessment}
Goal Context:
{goal_context}
Retrieved Source Summary:
{retrieved_source_summary}
Identified Skill Requirements:
{skill_requirements}
Identified Skill Gaps:
{skill_gaps}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "completeness": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "gap_calibration": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "confidence_validity": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "expert_calibration": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_level_accuracy": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring rubric — higher is always better:
- completeness: Does the skill list cover ALL areas a learner needs for this goal, using retrieved course context as primary evidence when it exists?
    Score 5: the list is comprehensive and retrieved evidence is used well when available; no major skill area is missing.
    Score 4: coverage is strong with only one minor skill area missing, weakly specified, or slightly under-grounded.
    Score 3: coverage is partial — key areas are present, but at least one important area is incomplete, weakly represented, or weakly grounded.
    Score 2: one clearly major skill area is missing, or multiple important areas are weakly represented, though the list still covers a meaningful portion of the goal.
    Score 1: multiple major skill areas needed to achieve the goal are absent from the list, making the map unusable as a learning diagnosis.
- gap_calibration: Are the current_level and required_level values plausible given the learner's stated background, without using FSLSM/personality/motivation as level evidence?
    Score 5: every gap level is directly justified by allowed evidence in learner background or retrieved course context, with no reliance on disallowed preference/personality cues.
    Score 4: levels are mostly plausible with only minor calibration issues that do not materially distort the learning diagnosis.
    Score 3: calibration is mixed — several levels are plausible, but multiple assignments are questionable, weakly justified, or appear influenced by weak evidence.
    Score 2: calibration is poor — many levels are implausible, with only a small subset matching the stated background.
    Score 1: gap levels directly contradict the allowed evidence or rely on disallowed cues such as FSLSM/personality/motivation.
- confidence_validity: Are the level_confidence values appropriate given the information available?
    Score 5: confidence ratings match the certainty warranted by the available evidence and retrieval context.
    Score 4: confidence labels are generally appropriate, with only mild over- or under-confidence.
    Score 3: confidence quality is inconsistent — some ratings fit the evidence while others appear weakly justified.
    Score 2: confidence labels are mostly mismatched to available evidence, though not entirely arbitrary.
    Score 1: confidence values seem arbitrary or systematically wrong.
- expert_calibration: Is expert used or withheld consistently with the learner's demonstrated mastery and SOLO-style evidence?
    Score 5: expert is used or withheld correctly in all cases, with decisions matching extended-abstract style evidence rather than topic difficulty alone.
    Score 4: expert usage is mostly correct, with only one borderline case where assignment or withholding is arguable.
    Score 3: expert usage is mixed — some skills are calibrated correctly, but multiple expert-level decisions are debatable.
    Score 2: expert usage is largely incorrect — expert is frequently overused or withheld in ways that conflict with evidence.
    Score 1: expert decisions systematically contradict the learner evidence.
- solo_level_accuracy: Are the current_level values consistent with the learner's stated experience and the prompt's allowed-evidence policy?
    Score 5: all current_level values match what the learner's stated experience and allowed evidence directly imply.
    Score 4: most level assignments align with the evidence, with only minor mismatches on edge cases.
    Score 3: level assignments are partly aligned; there is a mix of reasonable and questionable mappings.
    Score 2: level assignments are mostly misaligned, with only a few plausibly tied to stated experience.
    Score 1: current_level values systematically contradict the learner's stated experience or the allowed-evidence policy.

Important: verify that your score and reason are consistent before writing the JSON.
A positive reason (for example "skills are comprehensive", "levels are well-grounded", "confidence matches the evidence") must map to a HIGH score (4 or 5).
A negative reason (for example "major skill areas are missing", "levels rely on preference cues", "confidence is arbitrary") must map to a LOW score (1 or 2)."""


def _base_payload(extra: dict) -> dict:
    payload = dict(extra)
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME
    return payload


def _api_learner_info(scenario: dict) -> str:
    return scenario.get("learner_information_enhanced", scenario["learner_information"])


def _is_ok_timing_entry(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("error"):
        return False
    if entry.get("status_code", 200) >= 400:
        return False
    return isinstance(entry.get("body"), dict)


def _evaluate_skill_gap_body(scenario: dict, skill_gap_body: dict) -> dict:
    refined_goal = extract_refined_goal(skill_gap_body)
    skill_reqs = extract_skill_requirements_summary(skill_gap_body)
    skill_gaps = extract_skill_gaps_summary(skill_gap_body)
    goal_assessment = extract_goal_assessment(skill_gap_body)
    goal_context = extract_goal_context(skill_gap_body)
    retrieved_sources = extract_retrieved_sources(skill_gap_body)
    retrieved_source_summary = {
        "retrieved_source_count": len(retrieved_sources),
        "requires_retrieval": bool(goal_assessment.get("requires_retrieval", False)),
        "source_types": sorted(
            {
                str(source.get("source_type", "")).lower()
                for source in retrieved_sources
                if isinstance(source, dict) and source.get("source_type")
            }
        ),
        "course_codes": sorted(
            {
                str(source.get("course_code", "")).lower()
                for source in retrieved_sources
                if isinstance(source, dict) and source.get("course_code")
            }
        ),
    }
    user_prompt = SHARED_JUDGE_USER.format(
        learning_goal=scenario["learning_goal"],
        learner_information=scenario["learner_information"],
        refined_goal=refined_goal,
        goal_assessment=json.dumps(goal_assessment, indent=2),
        goal_context=json.dumps(goal_context, indent=2),
        retrieved_source_summary=json.dumps(retrieved_source_summary, indent=2),
        skill_requirements=skill_reqs,
        skill_gaps=skill_gaps,
    )
    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)
    return {
        "scenario_id": scenario["id"],
        "version": VERSION_KEY,
        "raw_output": {
            "refined_goal": refined_goal,
            "skill_requirements": json.loads(skill_reqs),
            "skill_gaps": json.loads(skill_gaps),
            "goal_assessment": goal_assessment,
            "goal_context": goal_context,
            "retrieved_source_summary": retrieved_source_summary,
        },
        "scores": scores,
    }


def evaluate_scenario(scenario: dict, base_url: str, headers: dict[str, str]) -> dict:
    payload = _base_payload(
        {
            "learning_goal": scenario["learning_goal"],
            "learner_information": _api_learner_info(scenario),
        }
    )
    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                f"{base_url}/identify-skill-gap-with-info",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            skill_gap_body = response.json()
    except Exception as exc:
        return {"scenario_id": scenario["id"], "version": VERSION_KEY, "error": str(exc)}
    return _evaluate_skill_gap_body(scenario, skill_gap_body)


def run_eval_skill_gap(
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
    print(f"\n=== Skill Gap Eval: {VERSION_LABEL} ===")
    for scenario in scenarios:
        sid = scenario["id"]
        sg_timing = prefetched_index.get(sid, {}).get("identify_skill_gap")
        if _is_ok_timing_entry(sg_timing):
            print(f"  [{VERSION_KEY}] {sid} — judging (using prefetched /identify-skill-gap-with-info)...")
            result = _evaluate_skill_gap_body(scenario, sg_timing["body"])
            result["used_prefetched_api_output"] = True
        else:
            print(f"  [{VERSION_KEY}] {sid} — calling /identify-skill-gap-with-info...")
            result = evaluate_scenario(scenario, base_url, headers)
        results.append(result)
    return {VERSION_KEY: results}


def summarise(all_results: dict) -> dict:
    dims = [
        "completeness",
        "gap_calibration",
        "confidence_validity",
        "expert_calibration",
        "solo_level_accuracy",
    ]
    results = all_results.get(VERSION_KEY, [])
    scores_list = [result.get("scores", {}) for result in results if "scores" in result]
    version_summary = {dim: average_score(scores_list, dim) for dim in dims}
    version_summary["scenario_count"] = len(results)
    version_summary["scored_scenario_count"] = len(scores_list)
    version_summary["error_count"] = sum(1 for result in results if "error" in result)
    version_summary["category_metadata"] = get_category_metadata("skill_gap")
    version_summary["metric_metadata"] = get_metric_metadata("skill_gap", dims)
    return {VERSION_KEY: version_summary}


if __name__ == "__main__":
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)

    all_results = run_eval_skill_gap(dataset["scenarios"])
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "skill_gap_results.json")
    with open(out_path, "w") as file:
        json.dump({"results": all_results, "summary": summary}, file, indent=2)

    print("\n=== Skill Gap Evaluation Summary ===")
    for dim, score in summary[VERSION_KEY].items():
        print(f"  {dim}: {score}")
    print(f"\nFull results saved to {out_path}")
