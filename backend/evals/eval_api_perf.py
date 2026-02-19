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
    skill_gaps_str = json.dumps(skill_gaps_body.get("skill_gaps", []))
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
            "learner_profile": json.dumps(profile_body),
            "session_count": DEFAULT_SESSION_COUNT,
        }),
    )


def run_explore_kps(base_url: str, profile_body: dict, path_body: dict) -> dict:
    sessions = path_body.get("learning_path", [])
    first_session = sessions[0] if sessions else {}
    return timed_post(
        httpx.Client(timeout=90.0),
        f"{base_url}/explore-knowledge-points",
        _base_payload({
            "learner_profile": json.dumps(profile_body),
            "learning_path": json.dumps(path_body),
            "learning_session": json.dumps(first_session),
        }),
    )


def run_tailor_content(base_url: str, profile_body: dict, path_body: dict) -> dict:
    sessions = path_body.get("learning_path", [])
    first_session = sessions[0] if sessions else {}
    return timed_post(
        httpx.Client(timeout=180.0),
        f"{base_url}/tailor-knowledge-content",
        _base_payload({
            "learner_profile": json.dumps(profile_body),
            "learning_path": json.dumps(path_body),
            "learning_session": json.dumps(first_session),
            "use_search": True,
            "allow_parallel": False,
            "with_quiz": True,
        }),
    )


def run_chat(base_url: str, profile_body: dict) -> dict:
    return timed_post(
        httpx.Client(timeout=60.0),
        f"{base_url}/chat-with-tutor",
        _base_payload({
            "messages": json.dumps([{"role": "user", "content": "What should I focus on first?"}]),
            "learner_profile": json.dumps(profile_body),
        }),
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

ENDPOINT_NAMES = [
    "refine_learning_goal",
    "identify_skill_gap",
    "create_learner_profile",
    "schedule_learning_path",
    "explore_knowledge_points",
    "tailor_knowledge_content",
    "chat_with_tutor",
]


def _api_learner_info(scenario: dict, version_key: str) -> str:
    """Return the version-specific prefixed learner_information for API calls."""
    key = f"learner_information_{version_key}"
    return scenario.get(key, scenario["learner_information"])


def run_scenario_perf(base_url: str, scenario: dict, version_key: str) -> dict[str, dict]:
    """Run the full pipeline for one scenario, returning timing per stage."""
    timings = {}

    # 1. Refine goal
    r = run_refine_goal(base_url, scenario, version_key)
    timings["refine_learning_goal"] = r

    # 2. Skill gap
    r = run_skill_gap(base_url, scenario, version_key)
    timings["identify_skill_gap"] = r
    sg_body = r.get("body") or {}

    # 3. Create profile
    r = run_create_profile(base_url, scenario, sg_body, version_key)
    timings["create_learner_profile"] = r
    profile_body = r.get("body") or {}

    # 4. Schedule path
    r = run_schedule_path(base_url, profile_body)
    timings["schedule_learning_path"] = r
    path_body = r.get("body") or {}

    # 5. Explore knowledge points
    r = run_explore_kps(base_url, profile_body, path_body)
    timings["explore_knowledge_points"] = r

    # 6. Full content generation (session 1)
    r = run_tailor_content(base_url, profile_body, path_body)
    timings["tailor_knowledge_content"] = r

    # 7. Chat
    r = run_chat(base_url, profile_body)
    timings["chat_with_tutor"] = r

    return timings


def run_eval_api_perf(scenarios: list[dict]) -> dict:
    all_results = {}

    for version_key, version_cfg in VERSIONS.items():
        print(f"\n=== API Perf: {version_cfg['label']} ===")
        base_url = version_cfg["base_url"]
        # Per-endpoint list of latency measurements
        endpoint_latencies: dict[str, list[float]] = {ep: [] for ep in ENDPOINT_NAMES}
        endpoint_errors: dict[str, int] = {ep: 0 for ep in ENDPOINT_NAMES}
        raw_runs = []

        for scenario in scenarios:
            sid = scenario["id"]
            print(f"  {sid} — running full pipeline timing...")
            try:
                timings = run_scenario_perf(base_url, scenario, version_key)
                raw_runs.append({"scenario_id": sid, "timings": timings})
                for ep, result in timings.items():
                    if ep in endpoint_latencies:
                        if result.get("error") or (result.get("status_code", 200) >= 400):
                            endpoint_errors[ep] += 1
                        else:
                            endpoint_latencies[ep].append(result["latency_ms"])
            except Exception as e:
                print(f"    FATAL ERROR for {sid}: {e}")
                raw_runs.append({"scenario_id": sid, "error": str(e)})

        # Compute summary stats per endpoint
        summary = {}
        n = len(scenarios)
        for ep in ENDPOINT_NAMES:
            lats = endpoint_latencies[ep]
            errs = endpoint_errors[ep]
            summary[ep] = {
                "p50_ms": compute_percentile(lats, 50),
                "p95_ms": compute_percentile(lats, 95),
                "error_rate_pct": round(errs / n * 100, 1) if n > 0 else 0.0,
                "sample_count": len(lats),
            }

        all_results[version_key] = {"raw_runs": raw_runs, "summary": summary}

    return all_results


if __name__ == "__main__":
    dataset_path = os.path.join(DATASETS_DIR, "shared_test_cases.json")
    with open(dataset_path) as f:
        dataset = json.load(f)
    scenarios = dataset["scenarios"]

    all_results = run_eval_api_perf(scenarios)

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
