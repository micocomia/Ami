"""
RAG Quality Evaluation — RAGAS

Evaluates metadata-targeted RAG cases using only the enhanced system.
RAGAS metrics include Context Precision, Context Recall, Faithfulness,
Answer Relevancy, and Answer Correctness.

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
import re

from evals.config import DATASETS_DIR, RESULTS_DIR

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

def build_rag_cases(dataset: dict) -> list[dict]:
    """
    Build metadata-targeted RAG evaluation cases from rag_metadata_cases.
    """
    cases = []
    for case in dataset.get("rag_metadata_cases", []):
        ground_truth_facts = [
            str(f).strip()
            for f in case.get("ground_truth_facts", [])
            if str(f).strip()
        ]
        if ground_truth_facts:
            ref_parts = [f if f.endswith((".", "!", "?")) else f"{f}." for f in ground_truth_facts]
            ground_truth = " ".join(ref_parts)
        else:
            ground_truth = case.get("ground_truth", "")
        cases.append({
            "goal_id": case.get("goal_id", "META"),
            "learning_goal": case["learning_goal"],
            "knowledge_point": case["knowledge_point"],
            "ground_truth": ground_truth,
            "ground_truth_facts": ground_truth_facts,
            "case_type": "metadata",
            "case_id": case.get("case_id", ""),
            "expected_course_code": case.get("expected_course_code", ""),
            "expected_keywords": case.get("expected_keywords", []),
            "query": case.get("query", ""),
            "expected_lecture_numbers": case.get("expected_lecture_numbers", []),
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
    question: str,
    ground_truth: str,
    case: dict | None = None,
) -> dict:
    """
    Extract (question, answer, contexts, ground_truth) for RAGAS.

    Enhanced returns:
      {"knowledge_draft": {"title": str, "content": str, "sources_used": [...]}}
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

    retrieval_query_primary = str(kd.get("retrieval_query_primary", "")).strip()
    retrieval_queries = [
        str(q).strip() for q in (kd.get("retrieval_queries") or [])
        if str(q).strip()
    ]
    retrieval_intent_text = str(kd.get("retrieval_intent_text", "")).strip()
    question_for_eval = retrieval_query_primary or question

    # Use retrieved source content when available. If schema changes or sources are
    # absent, fall back to draft text as a single context to keep evaluation robust.
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
        "question": question_for_eval,
        "answer": str(answer),
        "contexts": [str(c) for c in contexts],
        "ground_truth": ground_truth,
        "question_source": "retrieval_query" if retrieval_query_primary else "dataset_query",
        "dataset_query": question,
        "retrieval_query_primary": retrieval_query_primary,
        "retrieval_queries": retrieval_queries,
        "retrieval_intent_text": retrieval_intent_text,
    }
    if case:
        row["case_type"] = case.get("case_type", "metadata")
        row["case_id"] = case.get("case_id", "")
        row["expected_course_code"] = case.get("expected_course_code", "")
        row["expected_keywords"] = case.get("expected_keywords", [])
        row["expected_lecture_numbers"] = case.get("expected_lecture_numbers", [])
        row["ground_truth_facts"] = case.get("ground_truth_facts", [])
        row["source_types"] = [str(s.get("source_type", "")).lower() for s in sources if isinstance(s, dict)]
        row["source_course_codes"] = [str(s.get("course_code", "")).lower() for s in sources if isinstance(s, dict)]
        row["source_file_names"] = [str(s.get("file_name", "")).lower() for s in sources if isinstance(s, dict)]
        row["source_lecture_numbers"] = [
            int(s.get("lecture_number"))
            for s in sources
            if isinstance(s, dict) and str(s.get("lecture_number", "")).isdigit()
        ]
    return row


def _metadata_case_metrics(rows: list[dict]) -> dict:
    """Compute metadata-aware diagnostics on metadata-targeted RAG cases."""
    def _tokenize(text: str) -> set[str]:
        return {
            t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", str(text).lower())
            if len(t) > 2
        }

    def _fact_hit(fact: str, text: str) -> bool:
        f = str(fact).strip().lower()
        if not f:
            return False
        t = str(text).lower()
        if f in t:
            return True
        ft = _tokenize(f)
        if not ft:
            return False
        overlap = len(ft & _tokenize(t))
        return (overlap / len(ft)) >= 0.5

    def _to_int_set(values: list) -> set[int]:
        out = set()
        for v in values or []:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    def _lecture_from_file_name(file_name: str) -> int | None:
        m = re.search(r"lec_(\d+)\.pdf", str(file_name).lower())
        if m:
            return int(m.group(1))
        return None

    meta_rows = [r for r in rows if r.get("case_type") == "metadata" and "error" not in r]
    if not meta_rows:
        return {}

    hit_total = 0
    verified_total = 0
    keyword_cov_total = 0.0
    fact_cov_answer_total = 0.0
    fact_cov_context_total = 0.0
    fact_case_count = 0
    lecture_hit_total = 0
    lecture_case_count = 0

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

        facts = [str(f).strip() for f in row.get("ground_truth_facts", []) if str(f).strip()]
        if facts:
            fact_case_count += 1
            contexts_text = "\n".join(str(c) for c in row.get("contexts", []))
            answer_hits = sum(1 for f in facts if _fact_hit(f, answer_text))
            context_hits = sum(1 for f in facts if _fact_hit(f, contexts_text))
            fact_cov_answer_total += (answer_hits / len(facts))
            fact_cov_context_total += (context_hits / len(facts))

        expected_lectures = _to_int_set(row.get("expected_lecture_numbers", []))
        if expected_lectures:
            lecture_case_count += 1
            retrieved_lectures = _to_int_set(row.get("source_lecture_numbers", []))
            if not retrieved_lectures:
                for fn in row.get("source_file_names", []):
                    ln = _lecture_from_file_name(fn)
                    if ln is not None:
                        retrieved_lectures.add(ln)
            if expected_lectures.issubset(retrieved_lectures):
                lecture_hit_total += 1

    n = len(meta_rows)
    out = {
        "metadata_case_count": float(n),
        "metadata_course_hit_rate": hit_total / n,
        "metadata_verified_source_rate": verified_total / n,
    }
    if keyword_cov_total > 0:
        out["metadata_keyword_coverage"] = keyword_cov_total / n
    if fact_case_count > 0:
        out["metadata_fact_coverage_answer"] = fact_cov_answer_total / fact_case_count
        out["metadata_fact_coverage_context"] = fact_cov_context_total / fact_case_count
    if lecture_case_count > 0:
        out["metadata_expected_lecture_hit_rate"] = lecture_hit_total / lecture_case_count
    return out


def _verified_preflight_from_rows(rows: list[dict]) -> dict:
    """
    Lightweight preflight from existing evaluated rows (no additional API calls).
    Checks whether metadata-targeted rows show evidence that verified content was
    used by retrieval in enhanced product mode.
    """
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


def _ragas_mean_for_rows(rows: list[dict]) -> dict:
    """Compute mean RAGAS metrics for a prepared list of rows."""
    ragas_ready = [{
        "question": r["question"],
        "answer": r["answer"],
        "contexts": r["contexts"],
        "ground_truth": r["ground_truth"],
    } for r in rows]
    hf_dataset = HFDataset.from_list(ragas_ready)
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy, answer_correctness]
    result = ragas_evaluate(hf_dataset, metrics=metrics)
    return result.to_pandas().mean(numeric_only=True).to_dict()


def run_eval_rag(rag_cases: list[dict], checkpoint: dict) -> dict:
    """
    Build RAGAS rows for metadata-targeted RAG cases using enhanced drafts
    from the checkpoint (produced by eval_api_perf.run_eval_rag_drafts).
    No live API calls are made here.
    """
    version_key = "enhanced"
    print("\n=== RAG Eval: Enhanced (metadata cases only) ===")
    ragas_rows = []

    for case in rag_cases:
        dataset_query = case.get("query") or f"{case['learning_goal']} — {case['knowledge_point']}"
        print(f"  Loading: {case['knowledge_point'][:60]}...")
        draft_body = get_draft_from_checkpoint(checkpoint, version_key, case)
        if "error" in draft_body:
            print(f"    MISS: {draft_body['error']}")
            ragas_rows.append({
                "question": dataset_query,
                "answer": "",
                "contexts": [""],
                "ground_truth": case["ground_truth"],
                "question_source": "dataset_query",
                "dataset_query": dataset_query,
                "retrieval_query_primary": "",
                "retrieval_queries": [],
                "retrieval_intent_text": "",
                "case_type": case.get("case_type", "metadata"),
                "case_id": case.get("case_id", ""),
                "expected_course_code": case.get("expected_course_code", ""),
                "expected_keywords": case.get("expected_keywords", []),
                "expected_lecture_numbers": case.get("expected_lecture_numbers", []),
                "ground_truth_facts": case.get("ground_truth_facts", []),
                "error": draft_body["error"],
            })
        else:
            row = extract_ragas_fields(draft_body, dataset_query, case["ground_truth"], case=case)
            ragas_rows.append(row)

    return {"enhanced": ragas_rows}


def compute_ragas_scores(ragas_rows: list[dict]) -> dict:
    if not RAGAS_AVAILABLE:
        return {"error": "ragas not installed"}

    valid_rows = [r for r in ragas_rows if "error" not in r and r.get("answer")]
    if not valid_rows:
        return {"error": "No valid rows to evaluate"}

    summary = {"metrics_mode": "full_ragas", "evaluated_version": "enhanced", "case_scope": "metadata_only"}
    overall = _ragas_mean_for_rows(valid_rows)
    summary.update(overall)
    for k, v in overall.items():
        summary[f"metadata_{k}"] = v
    summary.update(_metadata_case_metrics(valid_rows))
    preflight = _verified_preflight_from_rows(valid_rows)
    summary["evaluation_mode"] = "enhanced_verified_content_only"
    summary["assumption"] = "metadata_queries_should_retrieve_verified_6_0001_content"
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
    print(f"Built {len(rag_cases)} metadata RAG evaluation cases")

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
        summary[version_key] = compute_ragas_scores(rows)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "rag_results.json")
    with open(out_path, "w") as f:
        json.dump({"raw_rows": all_results, "summary": summary}, f, indent=2)

    print("\n=== RAG Evaluation Summary ===")
    for version_key, scores in summary.items():
        print(f"\n{version_key}:")
        for metric, val in scores.items():
            if isinstance(val, float):
                print(f"  {metric}: {val:.3f}")

    print(f"\nFull results saved to {out_path}")
