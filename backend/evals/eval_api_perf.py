"""
API Performance Evaluation — Latency and Error Rate

Calls equivalent endpoints on both systems with the same inputs,
records latency per request, then reports p50/p95 and error rates.

Usage:
    python -m evals.eval_api_perf
"""

import json
import os
import httpx
from typing import Any

from evals.config import VERSIONS, DEFAULT_MODEL_PROVIDER, DEFAULT_MODEL_NAME, DATASETS_DIR, RESULTS_DIR, DEFAULT_SESSION_COUNT
from evals.utils.timing import timed_post, compute_percentile


def _base_payload(extra: dict) -> dict:
    payload = dict(extra)
    if DEFAULT_MODEL_PROVIDER:
        payload["model_provider"] = DEFAULT_MODEL_PROVIDER
    if DEFAULT_MODEL_NAME:
        payload["model_name"] = DEFAULT_MODEL_NAME
    return payload


# ---------------------------------------------------------------------------
# Endpoint runner functions
# ---------------------------------------------------------------------------

def run_refine_goal(base_url: str, scenario: dict, version_key: str) -> dict:
    return timed_post(
        httpx.Client(timeout=60.0),
        f"{base_url}/refine-learning-goal",
        _base_payload({
            "learning_goal": scenario["learning_goal"],
            "learner_information": _api_learner_info(scenario, version_key),
        }),
    )


def run_skill_gap(base_url: str, scenario: dict, version_key: str) -> dict:
    return timed_post(
        httpx.Client(timeout=90.0),
        f"{base_url}/identify-skill-gap-with-info",
        _base_payload({
            "learning_goal": scenario["learning_goal"],
            "learner_information": _api_learner_info(scenario, version_key),
        }),
    )


def run_create_profile(base_url: str, scenario: dict, skill_gaps_body: dict, version_key: str) -> dict:
    skill_gaps_str = repr(skill_gaps_body.get("skill_gaps", []))
    return timed_post(
        httpx.Client(timeout=90.0),
        f"{base_url}/create-learner-profile-with-info",
        _base_payload({
            "learning_goal": scenario["learning_goal"],
            "learner_information": _api_learner_info(scenario, version_key),
            "skill_gaps": skill_gaps_str,
        }),
    )


def run_schedule_path(base_url: str, profile_body: dict) -> dict:
    return timed_post(
        httpx.Client(timeout=90.0),
        f"{base_url}/schedule-learning-path",
        _base_payload({
            "learner_profile": repr(profile_body),
            "session_count": DEFAULT_SESSION_COUNT,
        }),
    )


def run_generate_learning_content(base_url: str, profile_body: dict, path_body: dict) -> dict:
    sessions = path_body.get("learning_path", [])
    first_session = sessions[0] if sessions else {}
    return timed_post(
        httpx.Client(timeout=240.0),
        f"{base_url}/generate-learning-content",
        _base_payload({
            "learner_profile": repr(profile_body),
            "learning_path": repr(path_body),
            "learning_session": repr(first_session),
            "use_search": True,
            "allow_parallel": True,
            "with_quiz": True,
            "method_name": "ami",
        }),
    )


def run_chat(base_url: str, profile_body: dict) -> dict:
    return timed_post(
        httpx.Client(timeout=60.0),
        f"{base_url}/chat-with-tutor",
        _base_payload({
            "messages": repr([{"role": "user", "content": "What should I focus on first?"}]),
            "learner_profile": repr(profile_body),
        }),
    )


def run_rag_draft_single_kp(base_url: str, profile_body: dict, path_body: dict, kp_name: str) -> dict:
    """Call /draft-knowledge-point for one RAG eval KP using real pipeline state."""
    sessions = path_body.get("learning_path", [])
    first_session = sessions[0] if sessions else {}
    kp_list = [{"name": kp_name, "role": "foundational", "solo_level": "beginner"}]
    return timed_post(
        httpx.Client(timeout=120.0),
        f"{base_url}/draft-knowledge-point",
        _base_payload({
            "learner_profile": repr(profile_body),
            "learning_path": repr(path_body),
            "learning_session": repr(first_session),
            "knowledge_points": repr(kp_list),
            "knowledge_point": repr(kp_list[0]),
            "use_search": True,
        }),
    )


def run_rag_draft_cases(
    base_url: str,
    version_key: str,
    rag_cases: list[dict],
    goal_id_to_scenario: dict[str, dict],
) -> dict[str, Any]:
    """
    Draft each RAG test case KP using real pipeline state (profile + learning path).
    Groups cases by goal_id so the pipeline runs once per learning goal.
    Returns {goal_id}_{knowledge_point} -> first knowledge_draft dict.
    """
    by_goal: dict[str, list[dict]] = {}
    for case in rag_cases:
        by_goal.setdefault(case["goal_id"], []).append(case)

    drafts: dict[str, Any] = {}

    for goal_id, cases in by_goal.items():
        scenario = goal_id_to_scenario.get(goal_id)
        if scenario is None:
            print(f"  WARNING: No scenario found for goal_id={goal_id}")
            for case in cases:
                drafts[f"{case['goal_id']}_{case['knowledge_point']}"] = {"error": "no_matching_scenario"}
            continue

        print(f"  Pipeline setup for goal_id={goal_id}: {scenario['learning_goal'][:60]}")
        try:
            sg_r = run_skill_gap(base_url, scenario, version_key)
            if sg_r.get("error") or sg_r.get("status_code", 200) >= 400:
                raise RuntimeError(f"skill_gap failed: {sg_r.get('error') or sg_r.get('status_code')}")
            sg_body = sg_r.get("body") or {}

            prof_r = run_create_profile(base_url, scenario, sg_body, version_key)
            if prof_r.get("error") or prof_r.get("status_code", 200) >= 400:
                raise RuntimeError(f"create_profile failed: {prof_r.get('error') or prof_r.get('status_code')}")
            profile_body = _unwrap_profile_body(prof_r.get("body") or {})

            path_r = run_schedule_path(base_url, profile_body)
            if path_r.get("error") or path_r.get("status_code", 200) >= 400:
                raise RuntimeError(f"schedule_path failed: {path_r.get('error') or path_r.get('status_code')}")
            path_body = path_r.get("body") or {}
        except Exception as e:
            print(f"    Pipeline setup failed: {e}")
            for case in cases:
                drafts[f"{case['goal_id']}_{case['knowledge_point']}"] = {"error": str(e)}
            continue

        for case in cases:
            kp_name = case["knowledge_point"]
            key = f"{case['goal_id']}_{kp_name}"
            print(f"    Drafting: {kp_name[:60]}")
            try:
                r = run_rag_draft_single_kp(base_url, profile_body, path_body, kp_name)
                if r.get("error") or r.get("status_code", 200) >= 400:
                    drafts[key] = {"error": r.get("error") or f"http_{r.get('status_code')}"}
                else:
                    drafts[key] = (r.get("body") or {}).get("knowledge_draft", {})
            except Exception as e:
                print(f"    ERROR: {e}")
                drafts[key] = {"error": str(e)}

    return drafts


def run_eval_rag_drafts(
    rag_cases: list[dict],
    dataset: dict,
    cache_path: str | None = None,
    resume: bool = False,
) -> dict[str, dict]:
    """
    Run pipeline-backed /draft-knowledge-point for every RAG test case KP on enhanced only.
    Saves results under rag_drafts in the checkpoint file.

    goal_id_to_scenario maps G1-G4 and META_60001 to a representative scenario so the
    pipeline (skill gap → create profile → schedule path) can be run with valid inputs.
    META_60001 prefers S4 (non-tech 6.0001 scenario) and falls back to G2 if needed.
    """
    existing = _load_perf_cache(cache_path) if (resume and cache_path) else {}

    # Build goal_id -> scenario from the dataset
    learning_goals: dict[str, str] = dataset.get("learning_goals", {})
    scenarios: list[dict] = dataset.get("scenarios", [])
    goal_id_to_scenario: dict[str, dict] = {}
    for s in scenarios:
        for gid, gtext in learning_goals.items():
            if gtext == s["learning_goal"] and gid not in goal_id_to_scenario:
                goal_id_to_scenario[gid] = s
    # Map metadata RAG cases to the non-tech 6.0001 scenario (S4) for stability.
    # Fallback to G2 representative if S4 is unavailable.
    s4 = next((s for s in scenarios if s.get("id") == "S4"), None)
    if s4 is not None:
        goal_id_to_scenario["META_60001"] = s4
    elif "G2" in goal_id_to_scenario:
        goal_id_to_scenario["META_60001"] = goal_id_to_scenario["G2"]

    all_rag_drafts: dict[str, dict] = {}

    rag_versions = [("enhanced", VERSIONS["enhanced"])] if "enhanced" in VERSIONS else []
    for version_key, version_cfg in rag_versions:
        print(f"\n=== RAG Drafts: {version_cfg['label']} ===")
        base_url = version_cfg["base_url"]

        cached_drafts = existing.get(version_key, {}).get("rag_drafts", {}) if resume else {}
        if cached_drafts:
            print(f"  Resuming: {len(cached_drafts)} KP(s) already cached.")

        # Only draft KPs not already successfully cached
        pending_cases = [
            c for c in rag_cases
            if not (resume and f"{c['goal_id']}_{c['knowledge_point']}" in cached_drafts
                    and "error" not in cached_drafts[f"{c['goal_id']}_{c['knowledge_point']}"])
        ]
        for c in rag_cases:
            if c not in pending_cases:
                print(f"  skip (cached): {c['goal_id']}_{c['knowledge_point']}")

        new_drafts = run_rag_draft_cases(base_url, version_key, pending_cases, goal_id_to_scenario) if pending_cases else {}
        merged = {**cached_drafts, **new_drafts}
        all_rag_drafts[version_key] = merged

        # Save incrementally after each version
        if cache_path:
            checkpoint = _load_perf_cache(cache_path) if os.path.exists(cache_path) else {}
            checkpoint.setdefault(version_key, {})["rag_drafts"] = merged
            _save_perf_cache(cache_path, checkpoint)
            print(f"  Checkpoint updated: {len(merged)} RAG draft(s) saved for {version_key}.")

    return all_rag_drafts


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

ENDPOINT_NAMES = [
    "refine_learning_goal",
    "identify_skill_gap",
    "create_learner_profile",
    "schedule_learning_path",
    "generate_learning_content",
    "chat_with_tutor",
]


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


def _load_perf_cache(cache_path: str) -> dict:
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path) as f:
            body = json.load(f)
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _save_perf_cache(cache_path: str, data: dict) -> None:
    if not cache_path:
        return
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)


def _is_skipped_result(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    return str(result.get("error", "")).startswith("skipped_upstream:")


def _skipped(stage: str) -> dict[str, Any]:
    return {
        "status_code": 0,
        "latency_ms": 0.0,
        "body": None,
        "error": f"skipped_upstream:{stage}",
    }


def _summarise_raw_runs(raw_runs: list[dict], scenario_count: int) -> dict[str, dict[str, Any]]:
    endpoint_latencies: dict[str, list[float]] = {ep: [] for ep in ENDPOINT_NAMES}
    endpoint_errors: dict[str, int] = {ep: 0 for ep in ENDPOINT_NAMES}
    endpoint_applicable: dict[str, int] = {ep: 0 for ep in ENDPOINT_NAMES}
    endpoint_skipped: dict[str, int] = {ep: 0 for ep in ENDPOINT_NAMES}

    for run in raw_runs:
        timings = run.get("timings", {})
        if not isinstance(timings, dict):
            continue
        for ep, result in timings.items():
            if ep not in endpoint_latencies:
                continue
            if _is_skipped_result(result):
                endpoint_skipped[ep] += 1
                continue
            endpoint_applicable[ep] += 1
            if not isinstance(result, dict) or result.get("error") or (result.get("status_code", 200) >= 400):
                endpoint_errors[ep] += 1
            else:
                endpoint_latencies[ep].append(result.get("latency_ms", 0.0))

    summary = {}
    n = scenario_count
    for ep in ENDPOINT_NAMES:
        lats = endpoint_latencies[ep]
        errs = endpoint_errors[ep]
        applicable_n = endpoint_applicable[ep]
        summary[ep] = {
            "p50_ms": compute_percentile(lats, 50),
            "p95_ms": compute_percentile(lats, 95),
            "error_rate_pct": round(errs / applicable_n * 100, 1) if applicable_n > 0 else 0.0,
            "sample_count": len(lats),
            "applicable_count": applicable_n,
            "skipped_count": endpoint_skipped[ep],
        }
    return summary


def run_scenario_perf(base_url: str, scenario: dict, version_key: str) -> dict[str, dict]:
    """Run the full pipeline for one scenario, returning timing per stage."""
    timings = {}

    # 1. Refine goal
    r = run_refine_goal(base_url, scenario, version_key)
    timings["refine_learning_goal"] = r
    refined_goal_forced = scenario["learning_goal"]
    if isinstance(r, dict) and not r.get("error") and (r.get("status_code", 200) < 400):
        body = r.get("body") or {}
        if isinstance(body, dict):
            refined_goal_forced = body.get("refined_goal") or body.get("learning_goal") or refined_goal_forced

    # 2. Skill gap
    r = run_skill_gap(base_url, scenario, version_key)
    timings["identify_skill_gap"] = r
    if r.get("error") or (r.get("status_code", 200) >= 400):
        timings["create_learner_profile"] = _skipped("identify_skill_gap")
        timings["schedule_learning_path"] = _skipped("create_learner_profile")
        timings["generate_learning_content"] = _skipped("schedule_learning_path")
        timings["chat_with_tutor"] = _skipped("create_learner_profile")
        return timings
    sg_body = r.get("body") or {}

    # 2b. GenMentor ablation support: identify skill gap after explicit refine.
    # Not part of ENDPOINT_NAMES/perf summary (kept in raw_runs for downstream reuse).
    if version_key == "genmentor":
        with httpx.Client(timeout=90.0) as client:
            timings["identify_skill_gap_forced_refine"] = timed_post(
                client,
                f"{base_url}/identify-skill-gap-with-info",
                _base_payload({
                    "learning_goal": refined_goal_forced,
                    "learner_information": _api_learner_info(scenario, version_key),
                }),
            )

    # 3. Create profile
    r = run_create_profile(base_url, scenario, sg_body, version_key)
    timings["create_learner_profile"] = r
    if r.get("error") or (r.get("status_code", 200) >= 400):
        timings["schedule_learning_path"] = _skipped("create_learner_profile")
        timings["generate_learning_content"] = _skipped("schedule_learning_path")
        timings["chat_with_tutor"] = _skipped("create_learner_profile")
        return timings
    profile_body = _unwrap_profile_body(r.get("body") or {})

    # 4. Schedule path
    r = run_schedule_path(base_url, profile_body)
    timings["schedule_learning_path"] = r
    if r.get("error") or (r.get("status_code", 200) >= 400):
        timings["generate_learning_content"] = _skipped("schedule_learning_path")
        timings["chat_with_tutor"] = _skipped("schedule_learning_path")
        return timings
    path_body = r.get("body") or {}

    # 5. Generate learning content (unified endpoint)
    r = run_generate_learning_content(base_url, profile_body, path_body)
    timings["generate_learning_content"] = r
    if r.get("error") or (r.get("status_code", 200) >= 400):
        timings["chat_with_tutor"] = _skipped("generate_learning_content")
        return timings

    # 6. Chat
    r = run_chat(base_url, profile_body)
    timings["chat_with_tutor"] = r

    return timings


def run_eval_api_perf(scenarios: list[dict], cache_path: str | None = None, resume: bool = False) -> dict:
    all_results = {}
    existing = _load_perf_cache(cache_path) if (resume and cache_path) else {}
    scenario_ids = {s["id"] for s in scenarios}

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== API Perf: {version_cfg['label']} ===")
        base_url = version_cfg["base_url"]
        raw_runs = []
        completed_ids = set()

        # Resume from compatible cached rows for this version/scenario set.
        if existing.get(version_key, {}).get("raw_runs"):
            for run in existing[version_key]["raw_runs"]:
                sid = run.get("scenario_id")
                if sid in scenario_ids:
                    raw_runs.append(run)
                    completed_ids.add(sid)
            if completed_ids:
                print(f"  Resuming from cache: {len(completed_ids)} scenario(s) already completed.")

        for scenario in scenarios:
            sid = scenario["id"]
            if sid in completed_ids:
                print(f"  {sid} — skip (cached)")
                continue
            print(f"  {sid} — running full pipeline timing...")
            try:
                timings = run_scenario_perf(base_url, scenario, version_key)
                raw_runs.append({"scenario_id": sid, "timings": timings})
            except Exception as e:
                print(f"    FATAL ERROR for {sid}: {e}")
                raw_runs.append({"scenario_id": sid, "error": str(e)})

            # Save incremental checkpoint after each scenario.
            if cache_path:
                partial = dict(existing)
                partial[version_key] = {
                    "raw_runs": raw_runs,
                    "summary": _summarise_raw_runs(raw_runs, len(scenarios)),
                }
                _save_perf_cache(cache_path, partial)
                existing = partial

        # Compute summary stats per endpoint from full raw_runs.
        summary = _summarise_raw_runs(raw_runs, len(scenarios))

        all_results[version_key] = {"raw_runs": raw_runs, "summary": summary}

    if cache_path:
        _save_perf_cache(cache_path, all_results)

    return all_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run API performance evaluation with optional resume cache")
    parser.add_argument("--resume", action="store_true", help="Resume from existing cache file")
    parser.add_argument("--rag-only", action="store_true", help="Skip endpoint timing; only run/fill missing RAG drafts")
    parser.add_argument(
        "--cache-path",
        type=str,
        default=os.path.join(RESULTS_DIR, "api_perf_checkpoint.json"),
        help="Path to save/load incremental perf checkpoints",
    )
    args = parser.parse_args()

    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)
    scenarios = dataset["scenarios"]

    if not args.rag_only:
        all_results = run_eval_api_perf(scenarios, cache_path=args.cache_path, resume=args.resume)

        os.makedirs(RESULTS_DIR, exist_ok=True)
        out_path = os.path.join(RESULTS_DIR, "api_perf_results.json")
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2)

        print("\n=== API Performance Summary ===")
        for version_key, data in all_results.items():
            print(f"\n{VERSIONS[version_key]['label']}:")
            for ep, stats in data["summary"].items():
                print(f"  {ep}: p50={stats['p50_ms']}ms  p95={stats['p95_ms']}ms  errors={stats['error_rate_pct']}%")

        print(f"\nFull results saved to {out_path}")

    # Also run pipeline-backed drafts for all RAG test case KPs.
    # Results are saved under rag_drafts in the same checkpoint file so eval_rag.py
    # can load from it instead of making direct (dummy-input) API calls.
    print("\n=== Running RAG draft cases (pipeline-backed) ===")
    rag_cases = []
    for case in dataset.get("rag_metadata_cases", []):
        rag_cases.append({
            "goal_id": case.get("goal_id", "META"),
            "learning_goal": case["learning_goal"],
            "knowledge_point": case["knowledge_point"],
        })
    print(f"Built {len(rag_cases)} RAG metadata draft case(s).")
    run_eval_rag_drafts(rag_cases, dataset, cache_path=args.cache_path, resume=args.resume or args.rag_only)
