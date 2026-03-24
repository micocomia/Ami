"""
Master evaluation runner.

Runs all 5 evaluation categories against both GenMentor and 5902Group5,
then produces a side-by-side comparison report.

Usage:
    # From backend/ directory:
    python -m evals.run_all [--skip-rag] [--skip-perf] [--scenarios S1,S2]

Arguments:
    --skip-rag      Skip RAGAS evaluation (saves ~5 min and API cost)
    --skip-perf     Skip API performance evaluation
    --scenarios     Comma-separated list of scenario IDs to run (default: all scenarios in dataset)

Environment variables required:
    GENMENTOR_BASE_URL   (default: http://localhost:8000)
    ENHANCED_BASE_URL    (default: http://localhost:8001)
    OPENAI_API_KEY       (or ANTHROPIC_API_KEY for judge calls)
"""

import argparse
import json
import os
from datetime import datetime

from evals.config import VERSIONS, DATASETS_DIR, RESULTS_DIR
from evals.eval_skill_gap import run_eval_skill_gap, summarise as summarise_skill_gap
from evals.eval_plan import run_eval_plan, summarise as summarise_plan
from evals.eval_content import run_eval_content, summarise as summarise_content
from evals.eval_api_perf import run_eval_api_perf


def load_dataset(scenario_filter: list[str] | None = None) -> dict:
    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)
    if scenario_filter:
        dataset["scenarios"] = [s for s in dataset["scenarios"] if s["id"] in scenario_filter]
    return dataset


def load_cached_rag_summary(rag_results_path: str) -> dict | None:
    """Load RAG summary from rag_results.json when RAG phase is skipped."""
    if not os.path.exists(rag_results_path):
        return None
    try:
        with open(rag_results_path) as f:
            body = json.load(f)
        summary = body.get("summary")
        return summary if isinstance(summary, dict) else None
    except Exception:
        return None


def format_score(val) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)


def delta_str(baseline, enhanced) -> str:
    if baseline is None or enhanced is None:
        return "—"
    diff = enhanced - baseline
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.2f}"


def build_report(
    sg_summary: dict,
    plan_summary: dict,
    content_summary: dict,
    perf_results: dict | None,
    rag_summary: dict | None,
    run_timestamp: str,
) -> str:
    lines = [
        "# Comparative Evaluation Report",
        f"*Generated: {run_timestamp}*",
        "",
        "GenMentor = baseline | 5902Group5 = enhanced",
        "",
    ]

    def version_label(k):
        return VERSIONS[k]["label"]

    def section_table(title: str, dimensions: list[str], baseline_scores: dict, enhanced_scores: dict,
                      enhanced_only_dims: list[str] | None = None):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Dimension | GenMentor | 5902Group5 | Delta |")
        lines.append("|---|---|---|---|")
        for dim in dimensions:
            b = baseline_scores.get(dim)
            e = enhanced_scores.get(dim)
            lines.append(f"| {dim} | {format_score(b)} | {format_score(e)} | {delta_str(b, e)} |")
        if enhanced_only_dims:
            for dim in enhanced_only_dims:
                e = enhanced_scores.get(dim)
                lines.append(f"| {dim} *(enhanced only)* | N/A | {format_score(e)} | — |")
        lines.append("")

    # 1. RAG
    if rag_summary:
        lines.append("## 1. RAG Quality (RAGAS, 0–1 scale, Product Mode)")
        lines.append("")
        lines.append("*Method note: enhanced has verified-course-content access; baseline is web-search driven.*")
        lines.append("")
        rag_dims = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
        rag_metadata_diag_dims = [
            "metadata_course_hit_rate",
            "metadata_verified_source_rate",
            "metadata_keyword_coverage",
            "metadata_fact_coverage_answer",
            "metadata_fact_coverage_context",
            "metadata_expected_lecture_hit_rate",
        ]
        b = rag_summary.get("genmentor", {})
        e = rag_summary.get("enhanced", {})

        lines.append("### Overall")
        lines.append("")
        lines.append("| Metric | GenMentor | 5902Group5 | Delta |")
        lines.append("|---|---|---|---|")
        for dim in rag_dims:
            bv = b.get(dim)
            ev = e.get(dim)
            lines.append(f"| {dim} | {format_score(bv)} | {format_score(ev)} | {delta_str(bv, ev)} |")
        lines.append("")

        lines.append("### Standard Cases Only")
        lines.append("")
        lines.append("| Metric | GenMentor | 5902Group5 | Delta |")
        lines.append("|---|---|---|---|")
        for dim in rag_dims:
            key = f"standard_{dim}"
            bv = b.get(key)
            ev = e.get(key)
            if bv is not None or ev is not None:
                lines.append(f"| {dim} | {format_score(bv)} | {format_score(ev)} | {delta_str(bv, ev)} |")
        lines.append("")

        lines.append("### Metadata Cases Only")
        lines.append("")
        lines.append("| Metric | GenMentor | 5902Group5 | Delta |")
        lines.append("|---|---|---|---|")
        for dim in rag_dims:
            key = f"metadata_{dim}"
            bv = b.get(key)
            ev = e.get(key)
            if bv is not None or ev is not None:
                lines.append(f"| {dim} | {format_score(bv)} | {format_score(ev)} | {delta_str(bv, ev)} |")
        lines.append("")

        lines.append("### Metadata Diagnostics")
        lines.append("")
        lines.append("| Metric | GenMentor | 5902Group5 | Delta |")
        lines.append("|---|---|---|---|")
        for dim in rag_metadata_diag_dims:
            bv = b.get(dim)
            ev = e.get(dim)
            if bv is not None or ev is not None:
                lines.append(f"| {dim} | {format_score(bv)} | {format_score(ev)} | {delta_str(bv, ev)} |")
        lines.append("")
    else:
        lines.append("## 1. RAG Quality (RAGAS) — *skipped*\n")

    # 2. Skill Gap
    b_sg = sg_summary.get("genmentor", {})
    e_sg = sg_summary.get("enhanced", {})
    a_sg = sg_summary.get("genmentor_forced_refine", {})
    section_table(
        "2. Skill Gap Quality (LLM-Judge, 1–5 scale)",
        ["completeness", "gap_calibration", "goal_refinement_quality", "confidence_validity"],
        b_sg, e_sg,
        enhanced_only_dims=["expert_calibration", "solo_level_accuracy"],
    )

    if a_sg:
        lines.append("### Skill-Gap Mini Ablation (Baseline vs Forced Refine vs Enhanced)")
        lines.append("")
        lines.append("| Dimension | GenMentor | GenMentor (Forced Refine) | 5902Group5 |")
        lines.append("|---|---|---|---|")
        for dim in ["completeness", "gap_calibration", "goal_refinement_quality", "confidence_validity"]:
            lines.append(
                f"| {dim} | {format_score(b_sg.get(dim))} | {format_score(a_sg.get(dim))} | {format_score(e_sg.get(dim))} |"
            )
        lines.append("")

    # 3. Learning Plan
    b_plan = plan_summary.get("genmentor", {})
    e_plan = plan_summary.get("enhanced", {})
    section_table(
        "3. Learning Plan Quality (LLM-Judge, 1–5 scale)",
        ["pedagogical_sequencing", "skill_coverage", "scope_appropriateness", "session_abstraction_quality"],
        b_plan, e_plan,
        enhanced_only_dims=["fslsm_structural_alignment", "solo_outcome_progression"],
    )

    # 4. Content
    b_c = content_summary.get("genmentor", {})
    e_c = content_summary.get("enhanced", {})
    section_table(
        "4. Content Quality (LLM-Judge, 1–5 scale)",
        ["cognitive_level_match", "factual_accuracy", "quiz_alignment", "engagement_quality"],
        b_c, e_c,
        enhanced_only_dims=["fslsm_content_adaptation", "solo_cognitive_alignment"],
    )

    # 5. API Perf
    if perf_results:
        lines.append("## 5. API Performance (Latency in ms)")
        lines.append("")
        lines.append("| Endpoint | GenMentor p50 | GenMentor p95 | 5902Group5 p50 | 5902Group5 p95 | p50 Delta |")
        lines.append("|---|---|---|---|---|---|")
        b_perf = perf_results.get("genmentor", {}).get("summary", {})
        e_perf = perf_results.get("enhanced", {}).get("summary", {})
        all_eps = set(list(b_perf.keys()) + list(e_perf.keys()))
        for ep in sorted(all_eps):
            bv = b_perf.get(ep, {})
            ev = e_perf.get(ep, {})
            b50 = bv.get("p50_ms", 0)
            b95 = bv.get("p95_ms", 0)
            e50 = ev.get("p50_ms", 0)
            e95 = ev.get("p95_ms", 0)
            d50 = f"{e50 - b50:+.0f}" if b50 and e50 else "—"
            lines.append(f"| {ep} | {b50} | {b95} | {e50} | {e95} | {d50} |")
        lines.append("")

        lines.append("### Error Rates")
        lines.append("")
        lines.append("| Endpoint | GenMentor error% | 5902Group5 error% |")
        lines.append("|---|---|---|")
        for ep in sorted(all_eps):
            be = b_perf.get(ep, {}).get("error_rate_pct", 0)
            ee = e_perf.get(ep, {}).get("error_rate_pct", 0)
            lines.append(f"| {ep} | {be}% | {ee}% |")
        lines.append("")
    else:
        lines.append("## 5. API Performance — *skipped*\n")

    # Summary
    lines.append("---")
    lines.append("## Overall Summary")
    lines.append("")

    shared_sg = ["completeness", "gap_calibration", "goal_refinement_quality", "confidence_validity"]
    shared_plan = ["pedagogical_sequencing", "skill_coverage", "scope_appropriateness", "session_abstraction_quality"]
    shared_content = ["cognitive_level_match", "factual_accuracy", "quiz_alignment", "engagement_quality"]

    def mean_of(d: dict, keys: list) -> float | None:
        vals = [d.get(k) for k in keys if d.get(k) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    b_overall = mean_of({**b_sg, **b_plan, **b_c}, shared_sg + shared_plan + shared_content)
    e_overall = mean_of({**e_sg, **e_plan, **e_c}, shared_sg + shared_plan + shared_content)

    lines.append(f"| Version | Shared-Dimension Average (1–5) |")
    lines.append("|---|---|")
    lines.append(f"| GenMentor (Baseline) | {format_score(b_overall)} |")
    lines.append(f"| 5902Group5 (Enhanced) | {format_score(e_overall)} |")
    lines.append(f"| Delta | {delta_str(b_overall, e_overall)} |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run comparative evaluation suite")
    parser.add_argument("--skip-rag", action="store_true", help="Skip RAGAS evaluation")
    parser.add_argument("--skip-perf", action="store_true", help="Skip API performance evaluation")
    parser.add_argument("--resume-perf", action="store_true", help="Resume API perf from local checkpoint cache")
    parser.add_argument(
        "--perf-cache-path",
        type=str,
        default=os.path.join(RESULTS_DIR, "api_perf_checkpoint.json"),
        help="Local cache path for incremental API perf results",
    )
    parser.add_argument("--scenarios", type=str, default=None, help="Comma-separated scenario IDs, e.g. S1,S2,S3")
    args = parser.parse_args()

    scenario_filter = args.scenarios.split(",") if args.scenarios else None
    dataset = load_dataset(scenario_filter)
    scenarios = dataset["scenarios"]
    print(f"Running evaluation on {len(scenarios)} scenarios: {[s['id'] for s in scenarios]}")

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- API Perf ---
    perf_results = None
    if not args.skip_perf:
        print("\n" + "="*60)
        print("PHASE 1: API Performance (also seeds shared endpoint cache)")
        print("="*60)
        perf_results = run_eval_api_perf(
            scenarios,
            cache_path=args.perf_cache_path,
            resume=args.resume_perf,
        )

    # --- Skill Gap ---
    print("\n" + "="*60)
    print("PHASE 2: Skill Gap Evaluation")
    print("="*60)
    sg_results = run_eval_skill_gap(scenarios, prefetched_runs=perf_results)
    sg_summary = summarise_skill_gap(sg_results)

    # --- Learning Plan ---
    print("\n" + "="*60)
    print("PHASE 3: Learning Plan Evaluation")
    print("="*60)
    plan_results = run_eval_plan(scenarios, prefetched_runs=perf_results)
    plan_summary = summarise_plan(plan_results)

    # --- Content ---
    print("\n" + "="*60)
    print("PHASE 4: Content Evaluation")
    print("="*60)
    content_results = run_eval_content(scenarios, prefetched_runs=perf_results)
    content_summary = summarise_content(content_results)

    # --- RAG ---
    rag_summary = None
    if not args.skip_rag:
        print("\n" + "="*60)
        print("PHASE 5: RAG Evaluation (RAGAS)")
        print("="*60)
        from evals.eval_rag import (
            build_rag_cases,
            run_eval_rag,
            compute_ragas_scores,
            load_rag_checkpoint,
        )
        rag_cases = build_rag_cases(dataset)
        rag_checkpoint = load_rag_checkpoint(args.perf_cache_path)
        if not rag_checkpoint:
            raise RuntimeError(
                f"RAG phase requires api_perf checkpoint with rag_drafts at: {args.perf_cache_path}"
            )
        rag_rows = run_eval_rag(rag_cases, rag_checkpoint)
        rag_summary = {v: compute_ragas_scores(rows) for v, rows in rag_rows.items()}
    else:
        rag_results_path = os.path.join(RESULTS_DIR, "rag_results.json")
        cached_rag_summary = load_cached_rag_summary(rag_results_path)
        if cached_rag_summary:
            print(f"Using cached RAG summary from {rag_results_path}")
            rag_summary = cached_rag_summary

    # --- Save raw results ---
    os.makedirs(RESULTS_DIR, exist_ok=True)
    raw_out = {
        "run_timestamp": run_ts,
        "scenarios_evaluated": [s["id"] for s in scenarios],
        "skill_gap": {"results": sg_results, "summary": sg_summary},
        "plan": {"results": plan_results, "summary": plan_summary},
        "content": {"results": content_results, "summary": content_summary},
        "rag": rag_summary,
        "api_perf": perf_results,
    }
    json_path = os.path.join(RESULTS_DIR, "comparison_report.json")
    with open(json_path, "w") as f:
        json.dump(raw_out, f, indent=2)

    # --- Build markdown report ---
    report_md = build_report(
        sg_summary, plan_summary, content_summary,
        perf_results, rag_summary, run_ts
    )
    md_path = os.path.join(RESULTS_DIR, "comparison_report.md")
    with open(md_path, "w") as f:
        f.write(report_md)

    print("\n" + "="*60)
    print("EVALUATION COMPLETE")
    print("="*60)
    print(f"JSON results: {json_path}")
    print(f"Markdown report: {md_path}")
    print()
    print(report_md)


if __name__ == "__main__":
    main()
