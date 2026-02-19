"""
RAG Quality Evaluation — RAGAS

Calls /draft-knowledge-point on both systems for ~27 (knowledge_point, learning_goal)
pairs and evaluates with RAGAS metrics: Context Precision, Context Recall,
Faithfulness, and Answer Relevancy.

Note: RAGAS itself makes LLM calls, so set OPENAI_API_KEY before running.

Usage:
    pip install ragas>=0.2.0
    python -m evals.eval_rag
"""

import json
import os
import httpx

from evals.config import VERSIONS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, DATASETS_DIR, RESULTS_DIR

# RAGAS imports (optional dependency)
try:
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        context_precision,
        context_recall,
        faithfulness,
        answer_relevancy,
    )
    from datasets import Dataset as HFDataset
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    print("WARNING: ragas not installed. Run: pip install ragas datasets")


def _base_payload(extra: dict) -> dict:
    payload = dict(extra)
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME
    return payload


def build_rag_cases(dataset: dict) -> list[dict]:
    """
    Build a flat list of RAG evaluation cases from the shared dataset.
    Each case: {scenario_id, learning_goal, knowledge_point, ground_truth}
    """
    cases = []
    goals = dataset["learning_goals"]
    kps = dataset["rag_knowledge_points"]
    gts = dataset["rag_ground_truths"]

    for goal_id, goal_text in goals.items():
        for kp in kps.get(goal_id, []):
            gt_key = f"{goal_id}_{kp}"
            cases.append({
                "goal_id": goal_id,
                "learning_goal": goal_text,
                "knowledge_point": kp,
                "ground_truth": gts.get(gt_key, ""),
            })
    return cases


def _dummy_profile(version_key: str, learning_goal: str) -> str:
    """
    Return a minimal JSON-serialized learner profile that matches each system's
    LearnerProfile schema exactly, avoiding validation errors and ensuring the
    endpoint's profile-parsing logic receives well-formed input.

    GenMentor schema (modules/adaptive_learner_modeling/schemas.py):
      learning_preferences: {content_style: str, activity_type: str}

    Enhanced schema (modules/learner_profiler/schemas.py):
      learning_preferences: {fslsm_dimensions: {fslsm_processing, fslsm_perception,
                                                  fslsm_input, fslsm_understanding},
                              additional_notes: str | None}
      goal_display_name: str (optional, defaults to "")

    FSLSM dimensions are set to neutral (0.0) because RAG retrieval is query-driven,
    not persona-driven.  Neutral values produce no formatting bias in the drafter hints
    (_visual_formatting_hints / _processing_perception_hints return generic instructions),
    keeping the comparison focused on retrieval quality.
    """
    common = {
        "learner_information": "Generic learner",
        "learning_goal": learning_goal,
        "cognitive_status": {
            "overall_progress": 0,
            "mastered_skills": [],
            "in_progress_skills": [],
        },
        "behavioral_patterns": {
            "system_usage_frequency": "daily",
            "session_duration_engagement": "medium",
        },
    }

    if version_key == "genmentor":
        common["learning_preferences"] = {
            "content_style": "mixed",
            "activity_type": "mixed",
        }
    else:
        # Enhanced system: requires fslsm_dimensions; goal_display_name defaults to ""
        common["goal_display_name"] = ""
        common["learning_preferences"] = {
            "fslsm_dimensions": {
                "fslsm_processing": 0.0,
                "fslsm_perception": 0.0,
                "fslsm_input": 0.0,
                "fslsm_understanding": 0.0,
            },
            "additional_notes": None,
        }

    return json.dumps(common)


def call_draft_knowledge_point(base_url: str, version_key: str, learning_goal: str, knowledge_point: str) -> dict:
    """
    Call /draft-knowledge-point with a version-correct dummy profile.
    Returns the full response body.
    """
    dummy_profile = _dummy_profile(version_key, learning_goal)
    dummy_path = json.dumps({"learning_path": [{"id": "Session 1", "title": learning_goal, "abstract": "", "if_learned": False}]})
    dummy_session = json.dumps({"id": "Session 1", "title": learning_goal, "abstract": "", "if_learned": False})
    dummy_kps = json.dumps({"knowledge_points": [{"name": knowledge_point, "type": "foundational"}]})

    payload = _base_payload({
        "learner_profile": dummy_profile,
        "learning_path": dummy_path,
        "learning_session": dummy_session,
        "knowledge_points": dummy_kps,
        "knowledge_point": knowledge_point,
        "use_search": True,
    })

    with httpx.Client(timeout=90.0) as client:
        resp = client.post(f"{base_url}/draft-knowledge-point", json=payload)
        resp.raise_for_status()
        return resp.json()


def extract_ragas_fields(draft_body: dict, version_key: str, question: str, ground_truth: str) -> dict:
    """
    Extract (question, answer, contexts, ground_truth) for RAGAS.

    Both systems return:
      {"knowledge_draft": {"title": str, "content": str, ...}}

    Enhanced additionally returns sources_used inside knowledge_draft:
      {"knowledge_draft": {"title": str, "content": str, "sources_used": [...]}}

    GenMentor has no sources_used field, so contexts fall back to the draft content.
    """
    kd = draft_body.get("knowledge_draft", {})
    if isinstance(kd, str):
        try:
            kd = json.loads(kd)
        except Exception:
            kd = {}

    answer = kd.get("content", "")
    if not answer:
        # Last-resort fallback if schema changes
        answer = draft_body.get("content", draft_body.get("draft", json.dumps(draft_body)))

    # Contexts: enhanced stores sources_used; GenMentor has no sources field
    sources = kd.get("sources_used") or []
    if sources and isinstance(sources[0], dict):
        contexts = [s.get("page_content", s.get("content", str(s))) for s in sources if s]
    else:
        contexts = []

    if not contexts:
        # Fall back to the draft text itself as a single context
        contexts = [str(answer)]

    return {
        "question": question,
        "answer": str(answer),
        "contexts": [str(c) for c in contexts],
        "ground_truth": ground_truth,
    }


def run_eval_rag(rag_cases: list[dict]) -> dict:
    all_results = {}

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== RAG Eval: {version_cfg['label']} ===")
        base_url = version_cfg["base_url"]
        ragas_rows = []

        for case in rag_cases:
            question = f"{case['learning_goal']} — {case['knowledge_point']}"
            print(f"  Drafting: {case['knowledge_point'][:60]}...")
            try:
                draft_body = call_draft_knowledge_point(base_url, version_key, case["learning_goal"], case["knowledge_point"])
                row = extract_ragas_fields(draft_body, version_key, question, case["ground_truth"])
                ragas_rows.append(row)
            except Exception as e:
                print(f"    ERROR: {e}")
                ragas_rows.append({
                    "question": question,
                    "answer": "",
                    "contexts": [""],
                    "ground_truth": case["ground_truth"],
                    "error": str(e),
                })

        all_results[version_key] = ragas_rows

    return all_results


def compute_ragas_scores(ragas_rows: list[dict]) -> dict:
    if not RAGAS_AVAILABLE:
        return {"error": "ragas not installed"}

    valid_rows = [r for r in ragas_rows if "error" not in r and r.get("answer")]
    if not valid_rows:
        return {"error": "No valid rows to evaluate"}

    hf_dataset = HFDataset.from_list(valid_rows)
    result = ragas_evaluate(
        hf_dataset,
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    )
    return result.to_pandas().mean().to_dict()


if __name__ == "__main__":
    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)

    rag_cases = build_rag_cases(dataset)
    print(f"Built {len(rag_cases)} RAG evaluation cases")

    all_results = run_eval_rag(rag_cases)

    summary = {}
    for version_key, rows in all_results.items():
        print(f"\nComputing RAGAS scores for {version_key}...")
        summary[version_key] = compute_ragas_scores(rows)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "rag_results.json")
    with open(out_path, "w") as f:
        json.dump({"raw_rows": all_results, "summary": summary}, f, indent=2)

    print("\n=== RAG Evaluation Summary ===")
    for version_key, scores in summary.items():
        print(f"\n{VERSIONS[version_key]['label']}:")
        for metric, val in scores.items():
            if isinstance(val, float):
                print(f"  {metric}: {val:.3f}")

    print(f"\nFull results saved to {out_path}")
