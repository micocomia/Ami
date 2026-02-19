"""
Content Generator Evaluation — LLM-as-a-Judge

For each scenario, runs the full pipeline through /tailor-knowledge-content
(which internally calls explore → draft → integrate → quiz) and judges the
result on shared and enhanced-only dimensions.

Usage:
    python -m evals.eval_content
"""

import json
import os
import httpx

from evals.config import VERSIONS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, DATASETS_DIR, RESULTS_DIR, DEFAULT_SESSION_COUNT
from evals.utils.llm_judge import judge, average_score
from evals.utils.schema_adapter import (
    extract_skill_gaps_summary,
    extract_fslsm_dimensions,
    extract_current_solo_level,
)

SHARED_JUDGE_SYSTEM = """\
You are an expert instructional designer and subject matter evaluator.
You will assess the quality of AI-generated personalized learning content.
Rate the content on specified dimensions using a 1-5 scale.
Respond ONLY with valid JSON matching the schema in the user prompt."""

SHARED_JUDGE_USER = """\
Learner Background: {learner_information}
Session Goal: {session_title}
Knowledge Points Covered: {knowledge_points}
Generated Content (markdown excerpt, first 3000 chars):
{content_excerpt}
Generated Quizzes:
{quizzes}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "cognitive_level_match": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "factual_accuracy": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "quiz_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "engagement_quality": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring rubric:
- cognitive_level_match: 1=assumes far too much/little prior knowledge, 5=perfectly calibrated to background
- factual_accuracy: 1=significant factual errors, 5=all claims accurate
- quiz_alignment: 1=quiz questions unrelated to content, 5=every question maps to a knowledge point in content
- engagement_quality: 1=dry/confusing/unsupported, 5=clear structure, appropriate depth, motivating examples"""

ENHANCED_JUDGE_USER_EXTENSION = """\

Also evaluate these enhanced-only dimensions:
FSLSM Dimensions: {fslsm_dimensions}
(Scale: -1.0 to +1.0; processing: -1=active, +1=reflective; perception: -1=sensing, +1=intuitive;
 input: -1=visual, +1=verbal; understanding: -1=sequential, +1=global)
Current SOLO Level: {solo_level}

{{
  "fslsm_content_adaptation": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_cognitive_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

FSLSM content adaptation guide:
- Visual learner (input ≤ -0.5): should include diagrams, tables, visual examples
- Verbal learner (input ≥ 0.5): text-heavy, narrative explanations
- Active learner (processing ≤ -0.5): hands-on exercises, code challenges, interactive elements
- Reflective learner (processing ≥ 0.5): reflection prompts, analysis tasks, compare-and-contrast
- Sensing learner (perception ≤ -0.5): concrete examples presented before abstract concepts
- Intuitive learner (perception ≥ 0.5): theory and concepts presented before concrete examples

SOLO cognitive alignment:
- Beginner (unistructural): simple definitions, one concept at a time
- Intermediate (multistructural): multiple concepts side-by-side, lists, comparisons
- Advanced (relational): integration, cause-effect, applying concepts to scenarios
- Expert (extended abstract): generalisation, critical evaluation, novel applications

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


def run_content_pipeline(base_url: str, learning_goal: str, learner_information: str) -> dict:
    """
    Run onboarding + content generation for the first session of the learning path.
    Returns dict with: profile_body, path_body, session, content_body
    """
    with httpx.Client(timeout=180.0) as client:
        # Skill gap
        sg_resp = client.post(
            f"{base_url}/identify-skill-gap-with-info",
            json=_base_payload({"learning_goal": learning_goal, "learner_information": learner_information}),
        )
        sg_resp.raise_for_status()
        sg_body = sg_resp.json()

        # Profile
        profile_resp = client.post(
            f"{base_url}/create-learner-profile-with-info",
            json=_base_payload({
                "learning_goal": learning_goal,
                "learner_information": learner_information,
                "skill_gaps": json.dumps(sg_body.get("skill_gaps", [])),
            }),
        )
        profile_resp.raise_for_status()
        profile_body = profile_resp.json()

        # Learning path
        path_resp = client.post(
            f"{base_url}/schedule-learning-path",
            json=_base_payload({
                "learner_profile": json.dumps(profile_body),
                "session_count": DEFAULT_SESSION_COUNT,
            }),
        )
        path_resp.raise_for_status()
        path_body = path_resp.json()

        sessions = path_body.get("learning_path", [])
        if not sessions:
            raise ValueError("No sessions in learning path")

        # Evaluate content for session 1 only (cost control)
        first_session = sessions[0]

        content_resp = client.post(
            f"{base_url}/tailor-knowledge-content",
            json=_base_payload({
                "learner_profile": json.dumps(profile_body),
                "learning_path": json.dumps(path_body),
                "learning_session": json.dumps(first_session),
                "use_search": True,
                "allow_parallel": False,
                "with_quiz": True,
            }),
        )
        content_resp.raise_for_status()
        content_body = content_resp.json()

    return {
        "profile_body": profile_body,
        "path_body": path_body,
        "session": first_session,
        "content_body": content_body,
    }


def evaluate_scenario(scenario: dict, version_key: str, version_cfg: dict) -> dict:
    sid = scenario["id"]
    goal = scenario["learning_goal"]
    info = scenario["learner_information"]           # plain text — for judge context only
    api_info = _api_learner_info(scenario, version_key)  # prefixed — for API calls
    base_url = version_cfg["base_url"]
    is_enhanced = version_cfg["has_fslsm"]

    print(f"  [{version_key}] {sid} — running content pipeline (session 1)...")
    try:
        pipeline_out = run_content_pipeline(base_url, goal, api_info)
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"scenario_id": sid, "version": version_key, "error": str(e)}

    profile_body = pipeline_out["profile_body"]
    session = pipeline_out["session"]
    content_body = pipeline_out["content_body"]

    # Extract content fields (structure may vary slightly)
    content_md = content_body.get("content", content_body.get("learning_document", ""))
    if isinstance(content_md, dict):
        content_md = json.dumps(content_md)
    content_excerpt = str(content_md)[:3000]

    quizzes = content_body.get("quizzes", content_body.get("quiz", []))
    knowledge_points = session.get("associated_skills", [])

    user_prompt = SHARED_JUDGE_USER.format(
        learner_information=info,
        session_title=session.get("title", "Session 1"),
        knowledge_points=json.dumps(knowledge_points, indent=2),
        content_excerpt=content_excerpt,
        quizzes=json.dumps(quizzes, indent=2)[:2000],
    )

    if is_enhanced:
        fslsm = extract_fslsm_dimensions(profile_body)
        solo_level = extract_current_solo_level(profile_body)
        user_prompt += "\n\n" + ENHANCED_JUDGE_USER_EXTENSION.format(
            fslsm_dimensions=json.dumps(fslsm, indent=2) if fslsm else "N/A",
            solo_level=solo_level,
        )

    print(f"  [{version_key}] {sid} — judging...")
    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)

    return {
        "scenario_id": sid,
        "version": version_key,
        "session_title": session.get("title"),
        "scores": scores,
    }


def run_eval_content(scenarios: list[dict]) -> dict:
    all_results = {}
    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== Content Eval: {version_cfg['label']} ===")
        version_results = []
        for scenario in scenarios:
            result = evaluate_scenario(scenario, version_key, version_cfg)
            version_results.append(result)
        all_results[version_key] = version_results
    return all_results


def summarise(all_results: dict) -> dict:
    shared_dims = ["cognitive_level_match", "factual_accuracy", "quiz_alignment", "engagement_quality"]
    enhanced_dims = ["fslsm_content_adaptation", "solo_cognitive_alignment"]
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

    all_results = run_eval_content(scenarios)
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "content_results.json")
    with open(out_path, "w") as f:
        json.dump({"results": all_results, "summary": summary}, f, indent=2)

    print("\n=== Content Evaluation Summary ===")
    for version_key, scores in summary.items():
        print(f"\n{VERSIONS[version_key]['label']}:")
        for dim, score in scores.items():
            print(f"  {dim}: {score}")

    print(f"\nFull results saved to {out_path}")
