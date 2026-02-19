"""
RAG Quality Evaluation — RAGAS

Calls /draft-knowledge-points on both systems for standard and metadata-aware
RAG cases, then evaluates with RAGAS metrics: Context Precision, Context Recall,
Faithfulness, and Answer Relevancy.

Methodology: product-mode asymmetric comparison.
- Enhanced system is expected to have access to pre-indexed verified course content.
- Baseline is expected to rely on web-search-driven retrieval at draft time.

For metadata-aware cases (e.g., course-code-targeted prompts such as 6.0001),
it also reports simple retrieval diagnostics based on source metadata:
  - metadata_course_hit_rate
  - metadata_verified_source_rate
  - metadata_keyword_coverage

Note: RAGAS itself makes LLM calls, so set OPENAI_API_KEY before running.

Usage:
    pip install ragas>=0.2.0
    python -m evals.eval_rag
"""

import json
import os

from evals.config import VERSIONS, DATASETS_DIR, RESULTS_DIR

# RAGAS imports (optional dependency)
try:
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        context_precision,
        context_recall,
        faithfulness,
        answer_relevancy,
        answer_correctness,
    )
    from datasets import Dataset as HFDataset
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    print("WARNING: ragas not installed. Run: pip install ragas datasets")

# Metrics that require real retrieved contexts (not answer-as-context fallback).
# Only run these for the enhanced system where page_content is present in sources_used.
CONTEXT_METRICS = ["context_precision", "context_recall", "faithfulness"]
# Metrics that only need question + answer + ground_truth — safe for both systems.
ANSWER_METRICS = ["answer_relevancy", "answer_correctness"]


def build_rag_cases(dataset: dict) -> list[dict]:
    """
    Build a flat list of RAG evaluation cases from the shared dataset.
    Supports two shapes:
      1) Legacy goal/kp maps via rag_knowledge_points + rag_ground_truths
      2) Explicit metadata-aware cases via rag_metadata_cases
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
                "case_type": "standard",
            })

    # Optional metadata-aware retrieval cases.
    # These are explicitly query-targeted (e.g., include a course code) so we can
    # quantify whether retrieval surfaces sources with matching metadata.
    for case in dataset.get("rag_metadata_cases", []):
        cases.append({
            "goal_id": case.get("goal_id", "META"),
            "learning_goal": case["learning_goal"],
            "knowledge_point": case["knowledge_point"],
            "ground_truth": case["ground_truth"],
            "case_type": "metadata",
            "case_id": case.get("case_id", ""),
            "expected_course_code": case.get("expected_course_code", ""),
            "expected_keywords": case.get("expected_keywords", []),
            "query": case.get("query", ""),
        })
    return cases


def load_rag_checkpoint(cache_path: str) -> dict:
    """Load the api_perf_checkpoint.json that contains rag_drafts produced by eval_api_perf."""
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path) as f:
            body = json.load(f)
        return body if isinstance(body, dict) else {}
    except Exception as e:
        print(f"WARNING: Could not load checkpoint from {cache_path}: {e}")
        return {}


def get_draft_from_checkpoint(checkpoint: dict, version_key: str, case: dict) -> dict:
    """
    Retrieve the pre-computed knowledge draft for a RAG case from the checkpoint.
    Key format matches eval_api_perf: {goal_id}_{knowledge_point}.
    Returns {"knowledge_draft": <draft_dict>} on success, {"error": ...} on miss.
    """
    key = f"{case['goal_id']}_{case['knowledge_point']}"
    rag_drafts = checkpoint.get(version_key, {}).get("rag_drafts", {})
    draft = rag_drafts.get(key)
    if draft is None:
        return {"error": f"key not found in checkpoint: {key}"}
    if "error" in draft:
        return {"error": draft["error"]}
    return {"knowledge_draft": draft}


def extract_ragas_fields(
    draft_body: dict,
    version_key: str,
    question: str,
    ground_truth: str,
    case: dict | None = None,
) -> dict:
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

    # Contexts: enhanced stores sources_used (metadata-first); GenMentor usually has no sources field.
    # Use source content only when actually present; otherwise fall back to answer text for both
    # systems to keep RAGAS inputs symmetric and interpretable.
    sources = kd.get("sources_used") or []
    contexts = []
    if sources and isinstance(sources[0], dict):
        for s in sources:
            if not isinstance(s, dict):
                continue
            c = s.get("page_content") or s.get("content")
            if c:
                contexts.append(str(c))

    if not contexts:
        # Fall back to the draft text itself as a single context
        contexts = [str(answer)]

    row = {
        "question": question,
        "answer": str(answer),
        "contexts": [str(c) for c in contexts],
        "ground_truth": ground_truth,
    }
    if case:
        row["case_type"] = case.get("case_type", "standard")
        row["case_id"] = case.get("case_id", "")
        row["expected_course_code"] = case.get("expected_course_code", "")
        row["expected_keywords"] = case.get("expected_keywords", [])
        row["source_types"] = [str(s.get("source_type", "")).lower() for s in sources if isinstance(s, dict)]
        row["source_course_codes"] = [str(s.get("course_code", "")).lower() for s in sources if isinstance(s, dict)]
    return row


def _metadata_case_metrics(rows: list[dict]) -> dict:
    """Compute metadata-aware diagnostics on metadata-targeted RAG cases."""
    meta_rows = [r for r in rows if r.get("case_type") == "metadata" and "error" not in r]
    if not meta_rows:
        return {}

    hit_total = 0
    verified_total = 0
    keyword_cov_total = 0.0

    for row in meta_rows:
        expected_course = str(row.get("expected_course_code", "")).lower().strip()
        source_codes = [c for c in row.get("source_course_codes", []) if c]
        source_types = [t for t in row.get("source_types", []) if t]
        answer_text = str(row.get("answer", "")).lower()

        if expected_course and expected_course in source_codes:
            hit_total += 1
        if "verified_content" in source_types:
            verified_total += 1

        expected_keywords = [str(k).lower().strip() for k in row.get("expected_keywords", []) if str(k).strip()]
        if expected_keywords:
            matched = sum(1 for k in expected_keywords if k in answer_text)
            keyword_cov_total += (matched / len(expected_keywords))

    n = len(meta_rows)
    out = {
        "metadata_case_count": float(n),
        "metadata_course_hit_rate": hit_total / n,
        "metadata_verified_source_rate": verified_total / n,
    }
    if keyword_cov_total > 0:
        out["metadata_keyword_coverage"] = keyword_cov_total / n
    return out


def _verified_preflight_from_rows(rows: list[dict], version_key: str) -> dict:
    """
    Lightweight preflight from existing evaluated rows (no additional API calls).
    Checks whether metadata-targeted rows show evidence that verified content was
    used by retrieval in enhanced product mode.
    """
    if version_key != "enhanced":
        return {
            "enabled": False,
            "passed": None,
            "reason": "baseline_web_only_expected",
            "probe_count": 0,
            "verified_source_hit_count": 0,
            "course_code_hit_count": 0,
        }

    meta_rows = [r for r in rows if r.get("case_type") == "metadata" and "error" not in r]
    probe_count = len(meta_rows)
    if probe_count == 0:
        return {
            "enabled": True,
            "passed": False,
            "reason": "no_metadata_rows_available",
            "probe_count": 0,
            "verified_source_hit_count": 0,
            "course_code_hit_count": 0,
        }

    verified_hits = 0
    course_hits = 0
    for r in meta_rows:
        source_types = [str(x).lower() for x in r.get("source_types", []) if x]
        source_codes = [str(x).lower() for x in r.get("source_course_codes", []) if x]
        expected_course = str(r.get("expected_course_code", "")).lower().strip()
        if "verified_content" in source_types:
            verified_hits += 1
        if expected_course and expected_course in source_codes:
            course_hits += 1

    passed = verified_hits > 0 and course_hits > 0
    return {
        "enabled": True,
        "passed": passed,
        "reason": "ok" if passed else "verified_content_or_course_code_not_observed",
        "probe_count": probe_count,
        "verified_source_hit_count": verified_hits,
        "course_code_hit_count": course_hits,
    }


def _ragas_mean_for_rows(rows: list[dict], use_context_metrics: bool = True) -> dict:
    """Compute mean RAGAS metrics for a prepared list of rows.

    When use_context_metrics=False (baseline), only answer_relevancy and
    answer_correctness are run — these don't require real retrieved contexts.
    """
    ragas_ready = [{
        "question": r["question"],
        "answer": r["answer"],
        "contexts": r["contexts"],
        "ground_truth": r["ground_truth"],
    } for r in rows]
    hf_dataset = HFDataset.from_list(ragas_ready)
    if use_context_metrics:
        metrics = [context_precision, context_recall, faithfulness, answer_relevancy, answer_correctness]
    else:
        metrics = [answer_relevancy, answer_correctness]
    result = ragas_evaluate(hf_dataset, metrics=metrics)
    return result.to_pandas().mean(numeric_only=True).to_dict()


def run_eval_rag(rag_cases: list[dict], checkpoint: dict) -> dict:
    """
    Build RAGAS rows for each RAG case by loading pre-computed drafts from the
    checkpoint (produced by eval_api_perf.run_eval_rag_drafts).  No live API calls
    are made here — the checkpoint must be populated first by running eval_api_perf.
    """
    all_results = {}

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== RAG Eval: {version_cfg['label']} ===")
        ragas_rows = []

        for case in rag_cases:
            question = case.get("query") or f"{case['learning_goal']} — {case['knowledge_point']}"
            print(f"  Loading: {case['knowledge_point'][:60]}...")
            draft_body = get_draft_from_checkpoint(checkpoint, version_key, case)
            if "error" in draft_body:
                print(f"    MISS: {draft_body['error']}")
                ragas_rows.append({
                    "question": question,
                    "answer": "",
                    "contexts": [""],
                    "ground_truth": case["ground_truth"],
                    "case_type": case.get("case_type", "standard"),
                    "case_id": case.get("case_id", ""),
                    "expected_course_code": case.get("expected_course_code", ""),
                    "expected_keywords": case.get("expected_keywords", []),
                    "error": draft_body["error"],
                })
            else:
                row = extract_ragas_fields(draft_body, version_key, question, case["ground_truth"], case=case)
                ragas_rows.append(row)

        all_results[version_key] = ragas_rows

    return all_results


def compute_ragas_scores(ragas_rows: list[dict], version_key: str | None = None) -> dict:
    if not RAGAS_AVAILABLE:
        return {"error": "ragas not installed"}

    valid_rows = [r for r in ragas_rows if "error" not in r and r.get("answer")]
    if not valid_rows:
        return {"error": "No valid rows to evaluate"}

    # Enhanced system has real retrieved contexts (page_content in sources_used).
    # Baseline falls back to answer-as-context, so context-dependent metrics are meaningless.
    use_context_metrics = (version_key == "enhanced")
    if not use_context_metrics:
        print(f"  Note: running answer-quality metrics only for {version_key} (no real retrieved contexts)")

    summary = {"metrics_mode": "full_ragas" if use_context_metrics else "answer_quality_only"}

    # Overall metrics (kept as top-level keys for backward compatibility).
    overall = _ragas_mean_for_rows(valid_rows, use_context_metrics=use_context_metrics)
    summary.update(overall)

    # Split metrics by case type.
    standard_rows = [r for r in valid_rows if r.get("case_type", "standard") == "standard"]
    metadata_rows = [r for r in valid_rows if r.get("case_type") == "metadata"]
    if standard_rows:
        standard_scores = _ragas_mean_for_rows(standard_rows, use_context_metrics=use_context_metrics)
        for k, v in standard_scores.items():
            summary[f"standard_{k}"] = v
    if metadata_rows:
        metadata_scores = _ragas_mean_for_rows(metadata_rows, use_context_metrics=use_context_metrics)
        for k, v in metadata_scores.items():
            summary[f"metadata_{k}"] = v

    summary.update(_metadata_case_metrics(valid_rows))
    if version_key:
        preflight = _verified_preflight_from_rows(valid_rows, version_key)
        summary["evaluation_mode"] = "product_asymmetric"
        summary["assumption"] = "enhanced_has_verified_course_content__baseline_web_search"
        summary["verified_preflight"] = preflight
        summary["verified_preflight_passed"] = preflight.get("passed")
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run RAG quality evaluation using RAGAS")
    parser.add_argument(
        "--cache-path",
        type=str,
        default=os.path.join(RESULTS_DIR, "api_perf_checkpoint.json"),
        help="Path to the api_perf checkpoint containing rag_drafts (produced by eval_api_perf)",
    )
    args = parser.parse_args()

    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)

    rag_cases = build_rag_cases(dataset)
    print(f"Built {len(rag_cases)} RAG evaluation cases")

    checkpoint = load_rag_checkpoint(args.cache_path)
    if not checkpoint:
        print(f"ERROR: No checkpoint found at {args.cache_path}.")
        print("Run eval_api_perf first to populate rag_drafts in the checkpoint.")
        raise SystemExit(1)

    missing = [
        c for c in rag_cases
        if not checkpoint.get("enhanced", {}).get("rag_drafts", {}).get(f"{c['goal_id']}_{c['knowledge_point']}")
    ]
    if missing:
        print(f"WARNING: {len(missing)} RAG case(s) missing from checkpoint — they will be skipped.")
        for c in missing:
            print(f"  missing: {c['goal_id']}_{c['knowledge_point']}")

    all_results = run_eval_rag(rag_cases, checkpoint)

    summary = {}
    for version_key, rows in all_results.items():
        print(f"\nComputing RAGAS scores for {version_key}...")
        summary[version_key] = compute_ragas_scores(rows, version_key=version_key)

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
