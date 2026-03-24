"""Tutor-based RAG evaluation for the current backend."""

import json
import os
import re

import httpx

from evals.Beta.auth import bootstrap_auth_headers
from evals.Beta.config import BETA_BASE_URL, DATASETS_DIR, RESULTS_DIR, VERSION_KEY
from evals.Beta.metric_metadata import get_category_metadata, get_metric_metadata

try:
    from datasets import Dataset as HFDataset
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import answer_correctness, answer_relevancy, context_precision, context_recall, faithfulness

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    print("WARNING: ragas not installed. Run: pip install ragas datasets")


def build_rag_cases(dataset: dict) -> list[dict]:
    cases = []
    for case in dataset.get("rag_metadata_cases", []):
        ground_truth_facts = [str(fact).strip() for fact in case.get("ground_truth_facts", []) if str(fact).strip()]
        if ground_truth_facts:
            ground_truth = " ".join(
                fact if fact.endswith((".", "!", "?")) else f"{fact}." for fact in ground_truth_facts
            )
        else:
            ground_truth = case.get("ground_truth", "")
        cases.append(
            {
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
            }
        )
    return cases


def extract_ragas_fields(chat_body: dict, question: str, ground_truth: str, case: dict | None = None) -> dict:
    trace = chat_body.get("retrieval_trace", {}) if isinstance(chat_body, dict) else {}
    raw_contexts = trace.get("contexts", []) if isinstance(trace, dict) else []
    contexts = []
    source_types = []
    source_course_codes = []
    source_file_names = []
    source_lecture_numbers = []
    for item in raw_contexts:
        if not isinstance(item, dict):
            continue
        page_content = str(item.get("page_content", "") or "")
        if page_content:
            contexts.append(page_content)
        source_types.append(str(item.get("source_type", "")).lower())
        source_course_codes.append(str(item.get("course_code", "")).lower())
        source_file_names.append(str(item.get("file_name", "")).lower())
        lecture_number = item.get("lecture_number")
        if isinstance(lecture_number, int):
            source_lecture_numbers.append(lecture_number)
        elif isinstance(lecture_number, str) and lecture_number.isdigit():
            source_lecture_numbers.append(int(lecture_number))

    row = {
        "question": question,
        "answer": str(chat_body.get("response", "") if isinstance(chat_body, dict) else ""),
        "contexts": contexts,
        "ground_truth": ground_truth,
        "question_source": "dataset_query",
        "dataset_query": question,
        "retrieval_query_primary": question,
        "retrieval_queries": [question],
        "retrieval_intent_text": "",
        "tool_calls": trace.get("tool_calls", []) if isinstance(trace, dict) else [],
    }
    if case:
        row.update(
            {
                "case_type": case.get("case_type", "metadata"),
                "case_id": case.get("case_id", ""),
                "expected_course_code": case.get("expected_course_code", ""),
                "expected_keywords": case.get("expected_keywords", []),
                "expected_lecture_numbers": case.get("expected_lecture_numbers", []),
                "ground_truth_facts": case.get("ground_truth_facts", []),
                "source_types": source_types,
                "source_course_codes": source_course_codes,
                "source_file_names": source_file_names,
                "source_lecture_numbers": source_lecture_numbers,
            }
        )
    return row


def _metadata_case_metrics(rows: list[dict]) -> dict:
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", str(text).lower()) if len(token) > 2}

    def _fact_hit(fact: str, text: str) -> bool:
        fact = str(fact).strip().lower()
        if not fact:
            return False
        haystack = str(text).lower()
        if fact in haystack:
            return True
        tokens = _tokenize(fact)
        return bool(tokens) and len(tokens & _tokenize(haystack)) / len(tokens) >= 0.5

    def _to_int_set(values: list) -> set[int]:
        out = set()
        for value in values or []:
            try:
                out.add(int(value))
            except Exception:
                continue
        return out

    def _lecture_from_file_name(file_name: str) -> int | None:
        match = re.search(r"lec_(\d+)\.pdf", str(file_name).lower())
        return int(match.group(1)) if match else None

    meta_rows = [row for row in rows if row.get("case_type") == "metadata" and "error" not in row]
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
        source_codes = [code for code in row.get("source_course_codes", []) if code]
        source_types = [source_type for source_type in row.get("source_types", []) if source_type]
        answer_text = str(row.get("answer", "")).lower()
        if expected_course and expected_course in source_codes:
            hit_total += 1
        if "verified_content" in source_types:
            verified_total += 1

        expected_keywords = [str(keyword).lower().strip() for keyword in row.get("expected_keywords", []) if str(keyword).strip()]
        if expected_keywords:
            matched = sum(1 for keyword in expected_keywords if keyword in answer_text)
            keyword_cov_total += matched / len(expected_keywords)

        facts = [str(fact).strip() for fact in row.get("ground_truth_facts", []) if str(fact).strip()]
        if facts:
            fact_case_count += 1
            contexts_text = "\n".join(str(context) for context in row.get("contexts", []))
            fact_cov_answer_total += sum(1 for fact in facts if _fact_hit(fact, answer_text)) / len(facts)
            fact_cov_context_total += sum(1 for fact in facts if _fact_hit(fact, contexts_text)) / len(facts)

        expected_lectures = _to_int_set(row.get("expected_lecture_numbers", []))
        if expected_lectures:
            lecture_case_count += 1
            retrieved_lectures = _to_int_set(row.get("source_lecture_numbers", []))
            if not retrieved_lectures:
                for file_name in row.get("source_file_names", []):
                    lecture_number = _lecture_from_file_name(file_name)
                    if lecture_number is not None:
                        retrieved_lectures.add(lecture_number)
            if expected_lectures.issubset(retrieved_lectures):
                lecture_hit_total += 1

    summary = {
        "metadata_case_count": float(len(meta_rows)),
        "metadata_course_hit_rate": hit_total / len(meta_rows),
        "metadata_verified_source_rate": verified_total / len(meta_rows),
    }
    if keyword_cov_total > 0:
        summary["metadata_keyword_coverage"] = keyword_cov_total / len(meta_rows)
    if fact_case_count > 0:
        summary["metadata_fact_coverage_answer"] = fact_cov_answer_total / fact_case_count
        summary["metadata_fact_coverage_context"] = fact_cov_context_total / fact_case_count
    if lecture_case_count > 0:
        summary["metadata_expected_lecture_hit_rate"] = lecture_hit_total / lecture_case_count
    return summary


def _verified_preflight_from_rows(rows: list[dict]) -> dict:
    meta_rows = [row for row in rows if row.get("case_type") == "metadata" and "error" not in row]
    if not meta_rows:
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
    for row in meta_rows:
        if "verified_content" in [str(item).lower() for item in row.get("source_types", []) if item]:
            verified_hits += 1
        expected_course = str(row.get("expected_course_code", "")).lower().strip()
        if expected_course and expected_course in [str(item).lower() for item in row.get("source_course_codes", []) if item]:
            course_hits += 1

    passed = verified_hits > 0 and course_hits > 0
    return {
        "enabled": True,
        "passed": passed,
        "reason": "ok" if passed else "verified_content_or_course_code_not_observed",
        "probe_count": len(meta_rows),
        "verified_source_hit_count": verified_hits,
        "course_code_hit_count": course_hits,
    }


def _ragas_mean_for_rows(rows: list[dict]) -> dict:
    dataset = HFDataset.from_list(
        [
            {
                "question": row["question"],
                "answer": row["answer"],
                "contexts": row["contexts"],
                "ground_truth": row["ground_truth"],
            }
            for row in rows
        ]
    )
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy, answer_correctness]
    result = ragas_evaluate(dataset, metrics=metrics)
    return result.to_pandas().mean(numeric_only=True).to_dict()


def run_eval_rag(rag_cases: list[dict], *, base_url: str = BETA_BASE_URL) -> dict:
    headers = bootstrap_auth_headers(base_url)
    rows = []
    print("\n=== RAG Eval: Current Backend via Tutor ===")
    with httpx.Client(timeout=120.0) as client:
        for case in rag_cases:
            query = case.get("query") or f"{case['learning_goal']} — {case['knowledge_point']}"
            print(f"  Querying: {case['knowledge_point'][:60]}...")
            payload = {
                "messages": json.dumps([{"role": "user", "content": query}]),
                "learner_profile": json.dumps({"learning_goal": case["learning_goal"]}),
                "learner_information": case.get("learning_goal", ""),
                "goal_context": {
                    "course_code": case.get("expected_course_code") or None,
                    "lecture_numbers": case.get("expected_lecture_numbers") or None,
                    "content_category": "Lectures" if case.get("expected_lecture_numbers") else None,
                },
                "use_vector_retrieval": True,
                "use_web_search": False,
                "use_media_search": False,
                "allow_preference_updates": False,
                "return_metadata": True,
            }
            try:
                response = client.post(f"{base_url}/chat-with-tutor", json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
                row = extract_ragas_fields(body, query, case["ground_truth"], case=case)
                if not row["answer"]:
                    row["error"] = "missing_tutor_response"
                elif not row["contexts"]:
                    row["error"] = "missing_retrieval_contexts"
                rows.append(row)
            except Exception as exc:
                rows.append(
                    {
                        "question": query,
                        "answer": "",
                        "contexts": [],
                        "ground_truth": case["ground_truth"],
                        "question_source": "dataset_query",
                        "dataset_query": query,
                        "retrieval_query_primary": query,
                        "retrieval_queries": [query],
                        "retrieval_intent_text": "",
                        "case_type": case.get("case_type", "metadata"),
                        "case_id": case.get("case_id", ""),
                        "expected_course_code": case.get("expected_course_code", ""),
                        "expected_keywords": case.get("expected_keywords", []),
                        "expected_lecture_numbers": case.get("expected_lecture_numbers", []),
                        "ground_truth_facts": case.get("ground_truth_facts", []),
                        "error": str(exc),
                    }
                )
    return {VERSION_KEY: rows}


def compute_ragas_scores(ragas_rows: list[dict]) -> dict:
    if not RAGAS_AVAILABLE:
        return {
            "error": "ragas not installed",
            "category_metadata": get_category_metadata("rag"),
            "metric_metadata": get_metric_metadata("rag"),
        }

    valid_rows = [row for row in ragas_rows if "error" not in row and row.get("answer") and row.get("contexts")]
    if not valid_rows:
        return {
            "error": "No valid rows to evaluate",
            "category_metadata": get_category_metadata("rag"),
            "metric_metadata": get_metric_metadata("rag"),
        }

    summary = {"metrics_mode": "full_ragas", "evaluated_version": VERSION_KEY, "case_scope": "metadata_only"}
    overall = _ragas_mean_for_rows(valid_rows)
    summary.update(overall)
    for key, value in overall.items():
        summary[f"metadata_{key}"] = value
    summary.update(_metadata_case_metrics(valid_rows))
    preflight = _verified_preflight_from_rows(valid_rows)
    summary["evaluation_mode"] = "tutor_vector_retrieval_only"
    summary["verified_preflight"] = preflight
    summary["verified_preflight_passed"] = preflight.get("passed")
    summary["category_metadata"] = get_category_metadata("rag")
    summary["metric_metadata"] = get_metric_metadata("rag")
    return summary


if __name__ == "__main__":
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)

    rag_cases = build_rag_cases(dataset)
    all_results = run_eval_rag(rag_cases)
    summary = {VERSION_KEY: compute_ragas_scores(all_results[VERSION_KEY])}

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "rag_results.json")
    with open(out_path, "w") as file:
        json.dump({"raw_rows": all_results, "summary": summary}, file, indent=2)

    print("\n=== RAG Evaluation Summary ===")
    for metric, value in summary[VERSION_KEY].items():
        if isinstance(value, float):
            print(f"  {metric}: {value:.3f}")
        else:
            print(f"  {metric}: {value}")
    print(f"\nFull results saved to {out_path}")
