"""Content evaluation for the current backend."""

import ast
import json
import os

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
    detect_content_contract_signals,
    extract_current_solo_level,
    extract_fslsm_dimensions,
    extract_quiz_counts,
)

SHARED_JUDGE_SYSTEM = """\
You are an expert instructional designer and subject matter evaluator.
You will assess the quality of AI-generated personalized learning content.
Rate the content on specified dimensions using a 1-5 scale.
Respond ONLY with valid JSON matching the schema in the user prompt."""

SHARED_JUDGE_USER = """\
Learner Background: {learner_information}
Session Goal: {session_title}
Selected Session JSON:
{learning_session}
Session Adaptation Contract:
{session_contract}
Knowledge Point Targets:
{knowledge_points}
Generated Content (markdown excerpt, first 3000 chars):
{content_excerpt}
Content Contract Signals:
{content_signals}
Generated Quizzes:
{quizzes}
Quiz Counts:
{quiz_counts}

Rate 1-5 for each dimension. Respond with JSON only:
{{
  "cognitive_level_match": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "factual_accuracy": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "quiz_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "engagement_quality": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "fslsm_content_adaptation": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_cognitive_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

Scoring guidance:
- cognitive_level_match: judge the content against the selected session outcomes and learner level, not against generic topic difficulty.
    Score 5: explanations, examples, and task depth are pitched at exactly the right level for the learner and selected session outcomes.
    Score 4: level match is strong overall, with only minor moments that are slightly too advanced or too basic.
    Score 3: level match is mixed — substantial parts fit, but noticeable sections are mismatched for the learner or selected session.
    Score 2: level match is weak — much of the content is inappropriately advanced or simplistic, with only limited useful sections.
    Score 1: the content is severely mismatched to the learner's level or selected session outcomes.
- factual_accuracy: reward source-grounded, internally consistent content; penalize unsupported or contradicted claims.
    Score 5: all material appears factually accurate, source-grounded, and internally consistent, with no misleading claims.
    Score 4: content is mostly accurate; any inaccuracies are minor and unlikely to mislead the learner's core understanding.
    Score 3: accuracy is mixed; there are some meaningful errors or unsupported claims, but key ideas are still partly correct.
    Score 2: accuracy is poor; multiple significant errors or unsupported claims affect important concepts.
    Score 1: the content contains clear factual errors or seriously misleading statements.
- quiz_alignment: judge whether the quizzes match the document and whether the question mix fits the current quiz SOLO rules.
    Score 5: quiz questions directly test concepts taught in the document and the question mix matches the intended SOLO-style assessment pattern.
    Score 4: most quiz questions align well, with only minor drift or a small mismatch in question-type depth.
    Score 3: alignment is partial — some questions fit the content, but several are weakly grounded or the mix is only loosely appropriate.
    Score 2: weak alignment — most questions are loosely related, poorly grounded, or mismatched to the intended depth.
    Score 1: the quiz is largely disconnected from the content or clearly violates the intended assessment depth.
- engagement_quality: judge active/reflection structure, practical relevance, and learner fit instead of output length or flourish.
    Score 5: the content has a clear flow, uses concrete learner-relevant support, and includes engagement structures that fit the session contract well.
    Score 4: content is generally clear and engaging, with good structure and some effective support, though a few sections are less polished.
    Score 3: engagement is inconsistent — structure or learner support is adequate in parts, but explanations or activities are uneven.
    Score 2: content is hard to follow for long stretches, with weak structure and limited learner-relevant support.
    Score 1: the content is disorganized, passive, or discouraging, with little usable learner support.
- fslsm_content_adaptation: judge whether the content preserves the session contract cues such as checkpoint challenges, reflection pauses, application-first/theory-first ordering, visual/verbal handling, and TTS-friendly phrasing when needed.
    Score 5: the content clearly preserves the contract-driven adaptation cues and matches the learner's FSLSM-driven session structure well.
    Score 4: adaptation is mostly aligned, with only minor omissions in one cue or dimension.
    Score 3: adaptation is partial — some required cues are preserved, but others are missing or weakly implemented.
    Score 2: adaptation is limited — most required cues are not preserved, with only occasional accidental alignment.
    Score 1: the content clearly contradicts the session contract or learner-adaptation requirements.
- solo_cognitive_alignment: judge whether the content and quizzes match the intended SOLO depth for the selected session outcomes.
    Score 5: the content and quizzes closely match the intended SOLO depth of the selected session outcomes.
    Score 4: cognitive demand is mostly appropriate, with only minor over- or under-shooting in a few sections or questions.
    Score 3: cognitive demand is uneven — some parts match the intended SOLO depth, while others are noticeably miscalibrated.
    Score 2: cognitive demand is largely misaligned, with only limited portions matching the intended SOLO depth.
    Score 1: the content and assessment are dramatically misaligned with the intended SOLO level.

Important: verify that your score and reason are consistent before writing the JSON.
A positive reason (for example "content is well-matched", "quiz directly tests taught concepts", "adaptation cues are preserved") must map to a HIGH score (4 or 5).
A negative reason (for example "content is too advanced", "unsupported claims appear", "contract cues are missing") must map to a LOW score (1 or 2).
"""


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


def _unwrap_learning_content_body(body: dict) -> dict:
    if not isinstance(body, dict):
        return {}
    wrapped = body.get("learning_content")
    return wrapped if isinstance(wrapped, dict) else body


def _build_session_contract(first_session: dict, profile_body: dict) -> dict:
    try:
        from modules.content_generator.utils.fslsm_adaptation import build_session_adaptation_contract

        return build_session_adaptation_contract(first_session or {}, profile_body or {})
    except Exception:
        return {}


def _knowledge_point_targets(first_session: dict) -> list[dict]:
    outcomes = first_session.get("desired_outcome_when_completed", []) if isinstance(first_session, dict) else []
    if not isinstance(outcomes, list):
        return []
    targets = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        name = str(outcome.get("name", "") or "").strip()
        level = str(outcome.get("level", "") or "").strip().lower()
        if name:
            targets.append({"name": name, "solo_level": level or "unknown"})
    return targets


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


def _evaluate_content_outputs(
    scenario: dict,
    sg_body: dict,
    profile_body: dict,
    path_body: dict,
    generated_body: dict,
) -> dict:
    skill_gap_count = _count_skill_gaps(sg_body)
    if skill_gap_count == 0:
        return {
            "scenario_id": scenario["id"],
            "version": VERSION_KEY,
            "not_applicable": True,
            "not_applicable_reason": "zero_skill_gaps",
            "pipeline_outputs": {"skill_gap_count": 0},
        }

    sessions = path_body.get("learning_path", [])
    first_session = sessions[0] if sessions else {}
    learning_content = _unwrap_learning_content_body(generated_body)
    content_md = learning_content.get("document", "")
    if isinstance(content_md, dict):
        content_md = json.dumps(content_md)
    quizzes = learning_content.get("quizzes", {})
    session_contract = _build_session_contract(first_session, profile_body)
    knowledge_point_targets = _knowledge_point_targets(first_session)
    quiz_counts = extract_quiz_counts(quizzes if isinstance(quizzes, dict) else {})
    content_signals = detect_content_contract_signals(content_md)
    fslsm = extract_fslsm_dimensions(profile_body)
    solo_level = extract_current_solo_level(profile_body)
    user_prompt = SHARED_JUDGE_USER.format(
        learner_information=scenario["learner_information"],
        session_title=first_session.get("title", "Session 1"),
        learning_session=json.dumps(first_session, indent=2),
        session_contract=json.dumps(session_contract, indent=2),
        knowledge_points=json.dumps(knowledge_point_targets or first_session.get("associated_skills", []), indent=2),
        content_excerpt=str(content_md)[:3000],
        content_signals=json.dumps(content_signals, indent=2),
        quizzes=json.dumps(quizzes, indent=2)[:2000],
        quiz_counts=json.dumps(quiz_counts, indent=2),
    )
    user_prompt += (
        f"\n\nFSLSM Dimensions: {json.dumps(fslsm, indent=2) if fslsm else 'N/A'}"
        f"\nCurrent SOLO Level: {solo_level}"
    )
    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)
    return {
        "scenario_id": scenario["id"],
        "version": VERSION_KEY,
        "session_title": first_session.get("title"),
        "pipeline_outputs": {
            "skill_gap_count": skill_gap_count,
            "selected_session": first_session,
            "session_adaptation_contract": session_contract,
            "knowledge_point_targets": knowledge_point_targets,
            "quiz_counts": quiz_counts,
            "content_contract_signals": content_signals,
        },
        "scores": scores,
    }


def evaluate_scenario(scenario: dict, base_url: str, headers: dict[str, str]) -> dict:
    with httpx.Client(timeout=300.0) as client:
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

            first_session = (path_body.get("learning_path") or [{}])[0]
            content_resp = client.post(
                f"{base_url}/generate-learning-content",
                json=_base_payload(
                    {
                        "learner_profile": json.dumps(profile_body),
                        "learning_path": json.dumps(path_body),
                        "learning_session": json.dumps(first_session),
                        "use_search": True,
                        "allow_parallel": True,
                        "with_quiz": True,
                    }
                ),
                headers=headers,
            )
            content_resp.raise_for_status()
            generated_body = content_resp.json()
        except Exception as exc:
            return {"scenario_id": scenario["id"], "version": VERSION_KEY, "error": str(exc)}
    return _evaluate_content_outputs(scenario, sg_body, profile_body, path_body, generated_body)


def run_eval_content(
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
    print(f"\n=== Content Eval: {VERSION_LABEL} ===")
    for scenario in scenarios:
        sid = scenario["id"]
        timings = prefetched_index.get(sid, {})
        sg_t = timings.get("identify_skill_gap")
        profile_t = timings.get("create_learner_profile")
        path_t = timings.get("schedule_learning_path")
        generate_t = timings.get("generate_learning_content")
        if all(_is_ok_timing_entry(entry) for entry in (sg_t, profile_t, path_t, generate_t)):
            print(f"  [{VERSION_KEY}] {sid} — judging (using prefetched content pipeline outputs)...")
            result = _evaluate_content_outputs(
                scenario,
                sg_t["body"],
                _unwrap_profile_body(profile_t["body"]),
                path_t["body"],
                generate_t["body"],
            )
            result["used_prefetched_api_output"] = True
        else:
            print(f"  [{VERSION_KEY}] {sid} — running content pipeline...")
            result = evaluate_scenario(scenario, base_url, headers)
        results.append(result)
    return {VERSION_KEY: results}


def summarise(all_results: dict) -> dict:
    dims = [
        "cognitive_level_match",
        "factual_accuracy",
        "quiz_alignment",
        "engagement_quality",
        "fslsm_content_adaptation",
        "solo_cognitive_alignment",
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
    version_summary["category_metadata"] = get_category_metadata("content")
    version_summary["metric_metadata"] = get_metric_metadata("content", dims)
    return {VERSION_KEY: version_summary}


if __name__ == "__main__":
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)

    all_results = run_eval_content(dataset["scenarios"])
    summary = summarise(all_results)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "content_results.json")
    with open(out_path, "w") as file:
        json.dump({"results": all_results, "summary": summary}, file, indent=2)

    print("\n=== Content Evaluation Summary ===")
    for dim, score in summary[VERSION_KEY].items():
        print(f"  {dim}: {score}")
    print(f"\nFull results saved to {out_path}")
