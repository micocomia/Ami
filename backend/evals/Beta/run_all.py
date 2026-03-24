"""Master runner for the Beta evaluation suite."""

import argparse
import json
import os
from datetime import datetime

from evals.Beta.config import DATASETS_DIR, RESULTS_DIR, VERSION_KEY, VERSION_LABEL
from evals.Beta.eval_api_perf import run_eval_api_perf
from evals.Beta.eval_content import run_eval_content, summarise as summarise_content
from evals.Beta.eval_plan import run_eval_plan, summarise as summarise_plan
from evals.Beta.eval_rag import build_rag_cases, compute_ragas_scores, run_eval_rag
from evals.Beta.eval_skill_gap import run_eval_skill_gap, summarise as summarise_skill_gap
from evals.Beta.metric_metadata import comparable_metrics_for, get_category_metadata


def load_dataset(scenario_filter: list[str] | None = None) -> dict:
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)
    if scenario_filter:
        dataset["scenarios"] = [scenario for scenario in dataset["scenarios"] if scenario["id"] in scenario_filter]
    return dataset


def load_cached_rag_summary(rag_results_path: str) -> dict | None:
    if not os.path.exists(rag_results_path):
        return None
    try:
        with open(rag_results_path) as file:
            body = json.load(file)
        summary = body.get("summary")
        return summary if isinstance(summary, dict) else None
    except Exception:
        return None


def format_score(value) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _mean_of(summary: dict, keys: list[str]) -> float | None:
    picked = [summary.get(key) for key in keys if summary.get(key) is not None]
    return round(sum(picked) / len(picked), 2) if picked else None


def _bridge_subset(summary: dict, category: str) -> dict:
    return {
        metric: summary.get(metric)
        for metric in comparable_metrics_for(category)
        if summary.get(metric) is not None
    }


def build_interpretation_payload(
    skill_gap_summary: dict,
    plan_summary: dict,
    content_summary: dict,
    rag_summary: dict | None,
) -> dict:
    current_skill_gap = skill_gap_summary.get(VERSION_KEY, {})
    current_plan = plan_summary.get(VERSION_KEY, {})
    current_content = content_summary.get(VERSION_KEY, {})
    current_rag = (rag_summary or {}).get(VERSION_KEY, {})

    return {
        "current_product": {
            "skill_gap": current_skill_gap,
            "plan": current_plan,
            "content": current_content,
            "rag": current_rag,
        },
        "bridge_subset": {
            "skill_gap": _bridge_subset(current_skill_gap, "skill_gap"),
            "plan": _bridge_subset(current_plan, "plan"),
            "content": _bridge_subset(current_content, "content"),
            "rag": _bridge_subset(current_rag, "rag"),
        },
        "comparability_notes": {
            category: get_category_metadata(category)
            for category in ("skill_gap", "plan", "content", "rag", "api_perf")
        },
    }


def _add_interpretation_table(lines: list[str], metric_metadata: dict) -> None:
    lines.extend(
        [
            "| Metric | Comparable to MVP? | Assessment Change in Beta | Why |",
            "|---|---|---|---|",
        ]
    )
    for metric, meta in metric_metadata.items():
        lines.append(
            f"| {metric} | {meta.get('comparable_to_mvp', 'N/A')} | "
            f"{meta.get('assessment_change_vs_mvp', '')} | {meta.get('assessment_change_reason', '')} |"
        )
    lines.append("")


def _add_single_section(lines: list[str], title: str, category: str, summary: dict, dims: list[str]) -> None:
    category_meta = summary.get("category_metadata", get_category_metadata(category))
    lines.extend([title, "", category_meta.get("current_product_note", ""), ""])
    lines.extend([f"Assessment changed vs MVP: {category_meta.get('mvp_change_note', '')}", ""])
    lines.extend(["| Dimension | Score |", "|---|---|"])
    for dim in dims:
        lines.append(f"| {dim} | {format_score(summary.get(dim))} |")
    lines.append(f"| scenario_count | {format_score(summary.get('scenario_count'))} |")
    lines.append(f"| scored_scenario_count | {format_score(summary.get('scored_scenario_count'))} |")
    if "not_applicable_zero_gap_count" in summary:
        lines.append(f"| not_applicable_zero_gap_count | {format_score(summary.get('not_applicable_zero_gap_count'))} |")
    lines.append(f"| error_count | {format_score(summary.get('error_count'))} |")
    lines.append("")
    if category == "plan" and "deterministic_plan_audit" in summary:
        audit = summary["deterministic_plan_audit"]
        lines.extend(
            [
                "| Deterministic Plan Audit | Count |",
                "|---|---|",
                f"| total_violation_count | {format_score(audit.get('total_violation_count'))} |",
                f"| total_coverage_gap_count | {format_score(audit.get('total_coverage_gap_count'))} |",
                f"| scenarios_with_violations | {format_score(audit.get('scenarios_with_violations'))} |",
                f"| scenarios_with_coverage_gaps | {format_score(audit.get('scenarios_with_coverage_gaps'))} |",
                f"| scenarios_with_flag_inconsistencies | {format_score(audit.get('scenarios_with_flag_inconsistencies'))} |",
                "",
            ]
        )
    _add_interpretation_table(lines, summary.get("metric_metadata", {}))


def build_report(
    skill_gap_summary: dict,
    plan_summary: dict,
    content_summary: dict,
    perf_results: dict | None,
    rag_summary: dict | None,
    run_timestamp: str,
) -> str:
    current_skill_gap = skill_gap_summary.get(VERSION_KEY, {})
    current_plan = plan_summary.get(VERSION_KEY, {})
    current_content = content_summary.get(VERSION_KEY, {})
    current_perf = (perf_results or {}).get(VERSION_KEY, {}).get("summary", {})
    current_rag = (rag_summary or {}).get(VERSION_KEY, {})
    guide_path = os.path.join(os.path.dirname(__file__), "evaluation_guide.md")

    lines = [
        "# Beta Evaluation Report",
        f"*Generated: {run_timestamp}*",
        "",
        VERSION_LABEL,
        "",
        "Beta is the canonical scorecard for the current backend. Metric names are retained where possible, but "
        "their interpretation follows the current module prompt contracts.",
        "",
        f"Interpretation guide: `{guide_path}`",
        "",
        "## Current Product Scorecard",
        "",
    ]

    if rag_summary:
        lines.extend(
            [
                "## 1. RAG Quality (RAGAS, 0-1 scale)",
                "",
                current_rag.get("category_metadata", {}).get("current_product_note", ""),
                "",
                f"Assessment changed vs MVP: {current_rag.get('category_metadata', {}).get('mvp_change_note', '')}",
                "",
                "| Metric | Score |",
                "|---|---|",
            ]
        )
        for metric in [
            "context_precision",
            "context_recall",
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
            "metadata_course_hit_rate",
            "metadata_verified_source_rate",
            "metadata_keyword_coverage",
            "metadata_fact_coverage_answer",
            "metadata_fact_coverage_context",
            "metadata_expected_lecture_hit_rate",
        ]:
            if metric in current_rag:
                lines.append(f"| {metric} | {format_score(current_rag.get(metric))} |")
        lines.append("")
        _add_interpretation_table(lines, current_rag.get("metric_metadata", {}))
    else:
        lines.append("## 1. RAG Quality (RAGAS) — *skipped*\n")

    _add_single_section(
        lines,
        "## 2. Skill Gap Quality (LLM-Judge, 1-5 scale)",
        "skill_gap",
        current_skill_gap,
        [
            "completeness",
            "gap_calibration",
            "confidence_validity",
            "expert_calibration",
            "solo_level_accuracy",
        ],
    )
    _add_single_section(
        lines,
        "## 3. Learning Plan Quality (LLM-Judge, 1-5 scale)",
        "plan",
        current_plan,
        [
            "pedagogical_sequencing",
            "skill_coverage",
            "scope_appropriateness",
            "session_abstraction_quality",
            "fslsm_structural_alignment",
            "solo_outcome_progression",
        ],
    )
    _add_single_section(
        lines,
        "## 4. Content Quality (LLM-Judge, 1-5 scale)",
        "content",
        current_content,
        [
            "cognitive_level_match",
            "factual_accuracy",
            "quiz_alignment",
            "engagement_quality",
            "fslsm_content_adaptation",
            "solo_cognitive_alignment",
        ],
    )

    if perf_results:
        perf_meta = get_category_metadata("api_perf")
        lines.extend(
            [
                "## 5. API Performance (Latency in ms)",
                "",
                perf_meta.get("current_product_note", ""),
                "",
                f"Assessment changed vs MVP: {perf_meta.get('mvp_change_note', '')}",
                "",
                "| Endpoint | p50 | p95 | error% | applicable_count | skipped_count |",
                "|---|---|---|---|---|---|",
            ]
        )
        for endpoint in sorted(current_perf.keys()):
            values = current_perf[endpoint]
            lines.append(
                "| {endpoint} | {p50} | {p95} | {error} | {applicable} | {skipped} |".format(
                    endpoint=endpoint,
                    p50=format_score(values.get("p50_ms")),
                    p95=format_score(values.get("p95_ms")),
                    error=format_score(values.get("error_rate_pct")),
                    applicable=format_score(values.get("applicable_count")),
                    skipped=format_score(values.get("skipped_count")),
                )
            )
        lines.append("")
    else:
        lines.append("## 5. API Performance — *skipped*\n")

    shared_skill_gap = ["completeness", "gap_calibration", "confidence_validity"]
    shared_plan = ["pedagogical_sequencing", "skill_coverage", "scope_appropriateness", "session_abstraction_quality"]
    shared_content = ["cognitive_level_match", "factual_accuracy", "quiz_alignment", "engagement_quality"]
    current_product_average = _mean_of(
        {**current_skill_gap, **current_plan, **current_content},
        shared_skill_gap + shared_plan + shared_content,
    )
    bridge_skill_gap = _bridge_subset(current_skill_gap, "skill_gap")
    bridge_plan = _bridge_subset(current_plan, "plan")
    bridge_content = _bridge_subset(current_content, "content")
    bridge_rag = _bridge_subset(current_rag, "rag")
    bridge_subset_average = _mean_of(
        {**bridge_skill_gap, **bridge_plan, **bridge_content, **bridge_rag},
        list(bridge_skill_gap) + list(bridge_plan) + list(bridge_content) + list(bridge_rag),
    )

    lines.extend(
        [
            "## Bridge Comparison to MVP",
            "",
            "Only metrics marked `yes` or `partial` are included here. This is a continuity view, not a claim that "
            "Beta should preserve MVP raw scores across changed product behaviors.",
            "",
            "| Category | Bridge Metrics Included |",
            "|---|---|",
            f"| Skill Gap | {', '.join(bridge_skill_gap.keys()) or 'none'} |",
            f"| Learning Plan | {', '.join(bridge_plan.keys()) or 'none'} |",
            f"| Content | {', '.join(bridge_content.keys()) or 'none'} |",
            f"| RAG | {', '.join(bridge_rag.keys()) or 'none'} |",
            "",
            "---",
            "## Overall Summary",
            "",
            "| Metric | Score |",
            "|---|---|",
            f"| current_product_average | {format_score(current_product_average)} |",
            f"| bridge_subset_average | {format_score(bridge_subset_average)} |",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run the Beta evaluation suite")
    parser.add_argument("--skip-rag", action="store_true", help="Skip RAGAS evaluation")
    parser.add_argument("--skip-perf", action="store_true", help="Skip API performance evaluation")
    parser.add_argument("--resume-perf", action="store_true", help="Resume API perf from local checkpoint cache")
    parser.add_argument(
        "--perf-cache-path",
        type=str,
        default=os.path.join(RESULTS_DIR, "api_perf_checkpoint.json"),
        help="Local cache path for incremental API perf results",
    )
    parser.add_argument("--scenarios", type=str, default=None, help="Comma-separated list of scenario IDs")
    args = parser.parse_args()

    dataset = load_dataset(args.scenarios.split(",") if args.scenarios else None)
    scenarios = dataset["scenarios"]
    print(f"Running Beta evaluation on {len(scenarios)} scenarios: {[scenario['id'] for scenario in scenarios]}")

    perf_results = None
    if not args.skip_perf:
        print("\n" + "=" * 60)
        print("PHASE 1: API Performance")
        print("=" * 60)
        perf_results = run_eval_api_perf(scenarios, cache_path=args.perf_cache_path, resume=args.resume_perf)

    print("\n" + "=" * 60)
    print("PHASE 2: Skill Gap Evaluation")
    print("=" * 60)
    skill_gap_results = run_eval_skill_gap(scenarios, prefetched_runs=perf_results)
    skill_gap_summary = summarise_skill_gap(skill_gap_results)

    print("\n" + "=" * 60)
    print("PHASE 3: Learning Plan Evaluation")
    print("=" * 60)
    plan_results = run_eval_plan(scenarios, prefetched_runs=perf_results)
    plan_summary = summarise_plan(plan_results)

    print("\n" + "=" * 60)
    print("PHASE 4: Content Evaluation")
    print("=" * 60)
    content_results = run_eval_content(scenarios, prefetched_runs=perf_results)
    content_summary = summarise_content(content_results)

    rag_summary = None
    if not args.skip_rag:
        print("\n" + "=" * 60)
        print("PHASE 5: RAG Evaluation")
        print("=" * 60)
        rag_rows = run_eval_rag(build_rag_cases(dataset))
        rag_summary = {VERSION_KEY: compute_ragas_scores(rag_rows[VERSION_KEY])}
    else:
        rag_summary = load_cached_rag_summary(os.path.join(RESULTS_DIR, "rag_results.json"))

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    interpretation = build_interpretation_payload(skill_gap_summary, plan_summary, content_summary, rag_summary)
    report_json = {
        "run_timestamp": run_timestamp,
        "scenarios_evaluated": [scenario["id"] for scenario in scenarios],
        "skill_gap": {"results": skill_gap_results, "summary": skill_gap_summary},
        "plan": {"results": plan_results, "summary": plan_summary},
        "content": {"results": content_results, "summary": content_summary},
        "rag": rag_summary,
        "api_perf": perf_results,
        **interpretation,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    json_path = os.path.join(RESULTS_DIR, "beta_report.json")
    with open(json_path, "w") as file:
        json.dump(report_json, file, indent=2)

    report_md = build_report(skill_gap_summary, plan_summary, content_summary, perf_results, rag_summary, run_timestamp)
    md_path = os.path.join(RESULTS_DIR, "beta_report.md")
    with open(md_path, "w") as file:
        file.write(report_md)

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    print(f"JSON results: {json_path}")
    print(f"Markdown report: {md_path}")
    print()
    print(report_md)


if __name__ == "__main__":
    main()
