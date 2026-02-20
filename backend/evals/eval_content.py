"""
Content Generator Evaluation — LLM-as-a-Judge

For each scenario, runs the full 4-stage content pipeline:
  1. explore-knowledge-points
  2. draft-knowledge-points
  3. integrate-learning-document
  4. generate-document-quizzes

This mirrors exactly what the frontend knowledge_document.py does in
render_content_preparation() for both the baseline (GenMentor) and the
enhanced (5902Group5) versions.  The assembled document and quizzes are
then judged on shared and enhanced-only dimensions.

Usage:
    python -m evals.eval_content
"""

import json
import os
import ast
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

Scoring rubric — higher is always better:
- cognitive_level_match: Does the content complexity match the learner's stated background?
    Score 5: explanations and examples are pitched at exactly the right level — neither over-simplified for an experienced learner nor assuming knowledge a beginner does not have.
    Score 4: level match is strong overall, with only minor moments that are slightly too advanced or too basic.
    Score 3: level match is mixed — substantial parts fit, but noticeable sections are mismatched for the learner.
    Score 2: level match is weak — much of the content is inappropriately advanced or simplistic, with only limited useful sections.
    Score 1: the content is severely mismatched — either far too advanced (assumes expertise the learner clearly lacks) or far too basic (condescendingly simple for a learner with stated experience).
- factual_accuracy: Are the claims made in the content correct?
    Score 5: all statements are factually accurate with no misleading simplifications or errors.
    Score 4: content is mostly accurate; any inaccuracies are minor and unlikely to mislead the learner's core understanding.
    Score 3: accuracy is mixed; there are some meaningful errors or oversimplifications, but key ideas are still partly correct.
    Score 2: accuracy is poor; multiple significant errors or misleading claims affect important concepts.
    Score 1: the content contains clear factual errors or significantly misleading statements that would cause the learner to form incorrect understanding.
- quiz_alignment: Do the quiz questions test concepts that were actually explained in this session's content?
    Score 5: every quiz question directly tests a concept or skill that was covered and explained in the content excerpt for this session.
    Score 4: most quiz questions align with explained concepts, with at most one minor drift into lightly covered material.
    Score 3: partial alignment; some questions are relevant, but several target concepts not clearly taught in the content.
    Score 2: weak alignment; most questions are loosely related or rely on concepts not properly explained.
    Score 1: the quiz questions ask about topics not covered in the content, or are entirely disconnected from the session's stated knowledge points.
- engagement_quality: Is the content clearly structured, well-explained, and supported by concrete examples?
    Score 5: the content has a logical flow, uses concrete examples to illustrate concepts, and is written in an accessible way that would motivate a learner to continue.
    Score 4: content is generally clear and engaging, with good structure and some concrete examples, though a few sections are less polished.
    Score 3: engagement is inconsistent; structure or clarity is adequate in parts, but explanations or examples are uneven.
    Score 2: content is hard to follow for long stretches, with weak structure and few useful examples.
    Score 1: the content is disorganised or relies on unexplained jargon, lacks any illustrative examples, or is written in a way that would actively discourage a learner.

Important: verify that your score and reason are consistent before writing the JSON.
A positive reason (e.g., "content well-matched", "all questions aligned") must map to a HIGH score (4 or 5).
A negative reason (e.g., "factual errors present", "quiz unrelated to content") must map to a LOW score (1 or 2)."""

ENHANCED_JUDGE_USER_EXTENSION = """\

Also evaluate these two enhanced-only dimensions and merge them into the same JSON object:
FSLSM Dimensions: {fslsm_dimensions}
(Scale: -1.0 to +1.0; processing: -1=active, +1=reflective; perception: -1=sensing, +1=intuitive;
 input: -1=visual, +1=verbal; understanding: -1=sequential, +1=global)
Current SOLO Level: {solo_level}

{{
  "fslsm_content_adaptation": {{"score": <int 1-5>, "reason": "<one sentence>"}},
  "solo_cognitive_alignment": {{"score": <int 1-5>, "reason": "<one sentence>"}}
}}

FSLSM content adaptation — check whether the content format reflects the learner's style preferences:
- Visual learner (input ≤ -0.5): content should include diagrams, tables, or visual examples
- Verbal learner (input ≥ 0.5): content should use text-heavy narrative explanations
- Active learner (processing ≤ -0.5): content should include hands-on exercises, code challenges, or interactive tasks
- Reflective learner (processing ≥ 0.5): content should include reflection prompts, analysis tasks, or compare-and-contrast sections
- Sensing learner (perception ≤ -0.5): concrete examples should appear before abstract concepts
- Intuitive learner (perception ≥ 0.5): theory and concepts should appear before concrete examples
- Balanced learner (all dimensions near 0.0): any well-structured mixed approach is acceptable

- fslsm_content_adaptation:
    Score 5: the content format clearly reflects the learner's FSLSM profile (e.g., a visual learner's content includes visual elements; an active learner's content includes exercises), or the learner is balanced and the content is well-structured overall.
    Score 4: adaptation is mostly aligned with FSLSM preferences, with only minor omissions in one dimension.
    Score 3: adaptation is partial — some style preferences are reflected, but others are missing or weakly implemented.
    Score 2: adaptation is limited — most FSLSM preferences are not reflected, with only occasional accidental alignment.
    Score 1: the content format directly contradicts the FSLSM profile (e.g., a visual learner receives pure text with no visual elements; an active learner receives only passive reading with no tasks).

SOLO cognitive alignment — does the content's cognitive demand match the learner's current level?
- unlearned / beginner (unistructural): simple definitions, one concept at a time, abundant concrete examples
- intermediate (multistructural): multiple concepts covered side-by-side, comparisons, structured lists
- advanced (relational): integration of concepts, cause-effect reasoning, applying knowledge to realistic scenarios
- expert (extended abstract): generalisation, critical evaluation, novel problem-solving beyond taught examples

- solo_cognitive_alignment:
    Score 5: the content's depth, complexity, and cognitive tasks closely match the learner's current SOLO level (e.g., a beginner receives clear definitions and simple examples; an advanced learner receives integration and application tasks).
    Score 4: cognitive demand is mostly appropriate, with minor over- or under-shooting in a few sections.
    Score 3: cognitive demand is uneven — some sections match SOLO level well, while others are noticeably miscalibrated.
    Score 2: cognitive demand is largely misaligned, with only limited portions matching the learner's SOLO level.
    Score 1: the content is dramatically misaligned with the current SOLO level (e.g., abstract critical evaluation tasks for a total beginner, or trivially simple definitions for a learner already at an advanced level).

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


def _prepare_markdown_document(document_structure, knowledge_points, knowledge_drafts) -> str:
    """
    Inline equivalent of the frontend's prepare_markdown_document().
    Converts the structured document dict returned by integrate-learning-document
    into a flat markdown string for use by the LLM judge.
    """
    if isinstance(document_structure, str):
        try:
            import ast
            document_structure = ast.literal_eval(document_structure)
        except Exception:
            return document_structure  # already a string, return as-is

    if not isinstance(document_structure, dict):
        return json.dumps(document_structure)

    part_titles = {
        "foundational": "## Foundational Concepts",
        "practical": "## Practical Applications",
        "strategic": "## Strategic Insights",
    }

    doc = f"# {document_structure.get('title', '')}"
    doc += f"\n\n{document_structure.get('overview', '')}"

    for k_type, part_title in part_titles.items():
        doc += f"\n\n{part_title}\n"
        for k_id, kp in enumerate(knowledge_points):
            if kp.get("type") != k_type:
                continue
            if k_id >= len(knowledge_drafts):
                continue
            kd = knowledge_drafts[k_id]
            doc += f"\n\n### {kd.get('title', '')}\n"
            doc += f"\n\n{kd.get('content', '')}\n"

    doc += f"\n\n## Summary\n\n{document_structure.get('summary', '')}"
    return doc


def run_content_pipeline(base_url: str, learning_goal: str, learner_information: str) -> dict:
    """
    Run onboarding + content generation for the first session of the learning path,
    mirroring the 4-stage pipeline in the frontend's render_content_preparation():
      Stage 1: explore-knowledge-points
      Stage 2: draft-knowledge-points
      Stage 3: integrate-learning-document
      Stage 4: generate-document-quizzes

    Returns dict with: profile_body, path_body, session, knowledge_points, content_body
    content_body keys: learning_document (markdown str), quizzes (dict)
    """
    with httpx.Client(timeout=300.0) as client:
        # Skill gap
        sg_resp = client.post(
            f"{base_url}/identify-skill-gap-with-info",
            json=_base_payload({"learning_goal": learning_goal, "learner_information": learner_information}),
        )
        sg_resp.raise_for_status()
        sg_body = sg_resp.json()
        skill_gap_count = _count_skill_gaps(sg_body)
        if skill_gap_count == 0:
            return {
                "not_applicable": True,
                "not_applicable_reason": "zero_skill_gaps",
                "skill_gaps_body": sg_body,
                "skill_gap_count": 0,
            }

        # Profile
        profile_resp = client.post(
            f"{base_url}/create-learner-profile-with-info",
            json=_base_payload({
                "learning_goal": learning_goal,
                "learner_information": learner_information,
                "skill_gaps": repr(sg_body.get("skill_gaps", [])),
            }),
        )
        profile_resp.raise_for_status()
        profile_body = _unwrap_profile_body(profile_resp.json())

        # Learning path
        path_resp = client.post(
            f"{base_url}/schedule-learning-path",
            json=_base_payload({
                "learner_profile": repr(profile_body),
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

        learner_profile_str = repr(profile_body)
        learning_path_str = repr(path_body)
        session_str = repr(first_session)

        # Stage 1/4: Explore knowledge points
        explore_resp = client.post(
            f"{base_url}/explore-knowledge-points",
            json=_base_payload({
                "learner_profile": learner_profile_str,
                "learning_path": learning_path_str,
                "learning_session": session_str,
            }),
        )
        explore_resp.raise_for_status()
        knowledge_points = explore_resp.json().get("knowledge_points", [])

        # Stage 2/4: Draft knowledge points
        draft_resp = client.post(
            f"{base_url}/draft-knowledge-points",
            json=_base_payload({
                "learner_profile": learner_profile_str,
                "learning_path": learning_path_str,
                "learning_session": session_str,
                "knowledge_points": json.dumps(knowledge_points),
                "use_search": True,
                "allow_parallel": False,
            }),
        )
        draft_resp.raise_for_status()
        knowledge_drafts = draft_resp.json().get("knowledge_drafts", [])

        # Stage 3/4: Integrate learning document
        integrate_resp = client.post(
            f"{base_url}/integrate-learning-document",
            json=_base_payload({
                "learner_profile": learner_profile_str,
                "learning_path": learning_path_str,
                "learning_session": session_str,
                "knowledge_points": json.dumps(knowledge_points),
                "knowledge_drafts": json.dumps(knowledge_drafts),
                "output_markdown": False,
            }),
        )
        integrate_resp.raise_for_status()
        integrate_body = integrate_resp.json()

        doc_structure = integrate_body.get("learning_document")
        document_is_markdown = integrate_body.get("document_is_markdown", False)

        if document_is_markdown or isinstance(doc_structure, str):
            learning_document = doc_structure or ""
        else:
            learning_document = _prepare_markdown_document(doc_structure, knowledge_points, knowledge_drafts)

        # Stage 4/4: Generate document quizzes
        quiz_resp = client.post(
            f"{base_url}/generate-document-quizzes",
            json=_base_payload({
                "learner_profile": learner_profile_str,
                "learning_document": str(learning_document),
                "single_choice_count": 3,
                "multiple_choice_count": 1,
                "true_false_count": 1,
                "short_answer_count": 1,
                "open_ended_count": 0,
            }),
        )
        quiz_resp.raise_for_status()
        quizzes = quiz_resp.json().get("document_quiz", {})

        content_body = {
            "learning_document": learning_document,
            "quizzes": quizzes,
        }

    return {
        "skill_gaps_body": sg_body,
        "skill_gap_count": skill_gap_count,
        "profile_body": profile_body,
        "path_body": path_body,
        "session": first_session,
        "knowledge_points": knowledge_points,
        "content_body": content_body,
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

    print(f"  [{version_key}] {sid} — running content pipeline (session 1)...")
    try:
        pipeline_out = run_content_pipeline(base_url, goal, api_info)
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"scenario_id": sid, "version": version_key, "error": str(e)}

    if pipeline_out.get("not_applicable_reason") == "zero_skill_gaps":
        return {
            "scenario_id": sid,
            "version": version_key,
            "not_applicable": True,
            "not_applicable_reason": "zero_skill_gaps",
            "pipeline_outputs": {
                "skill_gap_count": 0,
            },
        }

    profile_body = pipeline_out["profile_body"]
    session = pipeline_out["session"]
    explored_knowledge_points = pipeline_out.get("knowledge_points", [])
    content_body = pipeline_out["content_body"]

    # Extract content fields — content_body is always {"learning_document": str, "quizzes": dict}
    content_md = content_body.get("learning_document", "")
    if isinstance(content_md, dict):
        content_md = json.dumps(content_md)
    content_excerpt = str(content_md)[:3000]

    quizzes = content_body.get("quizzes", {})
    # Match frontend flow: this should reflect Stage-1 explored knowledge points.
    knowledge_points = explored_knowledge_points or session.get("associated_skills", [])

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
        "pipeline_outputs": {
            "skill_gap_count": pipeline_out.get("skill_gap_count"),
        },
        "scores": scores,
    }


def run_eval_content(scenarios: list[dict], prefetched_runs: dict | None = None) -> dict:
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
        print(f"\n=== Content Eval: {version_cfg['label']} ===")
        version_results = []
        for scenario in scenarios:
            sid = scenario["id"]
            timings = prefetched_index.get(version_key, {}).get(sid, {})
            sg_t = timings.get("identify_skill_gap")
            profile_t = timings.get("create_learner_profile")
            path_t = timings.get("schedule_learning_path")
            integrate_t = timings.get("integrate_learning_document")
            quiz_t = timings.get("generate_document_quizzes")

            if _is_ok_timing_entry(sg_t):
                skill_gap_count = _count_skill_gaps(sg_t["body"])
                if skill_gap_count == 0:
                    result = {
                        "scenario_id": sid,
                        "version": version_key,
                        "not_applicable": True,
                        "not_applicable_reason": "zero_skill_gaps",
                        "pipeline_outputs": {
                            "skill_gap_count": 0,
                        },
                        "used_prefetched_api_output": True,
                    }
                    version_results.append(result)
                    continue

            if (
                _is_ok_timing_entry(profile_t)
                and _is_ok_timing_entry(path_t)
                and _is_ok_timing_entry(integrate_t)
                and _is_ok_timing_entry(quiz_t)
            ):
                profile_body = _unwrap_profile_body(profile_t["body"])
                path_body = path_t["body"]
                sessions = path_body.get("learning_path", [])
                first_session = sessions[0] if sessions else {}
                explore_t = timings.get("explore_knowledge_points")
                integrate_body = integrate_t["body"] or {}
                learning_document = integrate_body.get("learning_document", "")
                quizzes = (quiz_t["body"] or {}).get("document_quiz", {})

                # Validate essential fields; otherwise fallback to live pipeline.
                if first_session and learning_document is not None:
                    # Keep formatting logic consistent with run_content_pipeline().
                    if not (integrate_body.get("document_is_markdown", False) or isinstance(learning_document, str)):
                        draft_t = timings.get("draft_knowledge_points")
                        if _is_ok_timing_entry(explore_t) and _is_ok_timing_entry(draft_t):
                            kp_list = (explore_t["body"] or {}).get("knowledge_points", [])
                            kd_list = (draft_t["body"] or {}).get("knowledge_drafts", [])
                            learning_document = _prepare_markdown_document(learning_document, kp_list, kd_list)

                    info = scenario["learner_information"]  # plain text — for judge context only
                    is_enhanced = version_cfg["has_fslsm"]

                    content_md = learning_document
                    if isinstance(content_md, dict):
                        content_md = json.dumps(content_md)
                    content_excerpt = str(content_md)[:3000]
                    explored_kps = (explore_t["body"] or {}).get("knowledge_points", []) if _is_ok_timing_entry(explore_t) else []
                    knowledge_points = explored_kps or first_session.get("associated_skills", [])

                    user_prompt = SHARED_JUDGE_USER.format(
                        learner_information=info,
                        session_title=first_session.get("title", "Session 1"),
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

                    print(f"  [{version_key}] {sid} — judging (using prefetched content pipeline outputs)...")
                    scores = judge(SHARED_JUDGE_SYSTEM, user_prompt)
                    result = {
                        "scenario_id": sid,
                        "version": version_key,
                        "session_title": first_session.get("title"),
                        "pipeline_outputs": {
                            "skill_gap_count": _count_skill_gaps(sg_t["body"]) if _is_ok_timing_entry(sg_t) else None,
                        },
                        "scores": scores,
                        "used_prefetched_api_output": True,
                    }
                else:
                    result = evaluate_scenario(scenario, version_key, version_cfg)
            else:
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
