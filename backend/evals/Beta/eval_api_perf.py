"""API performance evaluation for the current backend."""

import json
import os
from typing import Any

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
from evals.Beta.utils.timing import compute_percentile, timed_post

ENDPOINT_NAMES = [
    "refine_learning_goal",
    "identify_skill_gap",
    "create_learner_profile",
    "schedule_learning_path",
    "generate_learning_content",
    "chat_with_tutor",
]


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


def _load_perf_cache(cache_path: str) -> dict:
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path) as file:
            body = json.load(file)
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _save_perf_cache(cache_path: str, data: dict) -> None:
    if not cache_path:
        return
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as file:
        json.dump(data, file, indent=2)


def _is_skipped_result(result: dict | None) -> bool:
    return isinstance(result, dict) and str(result.get("error", "")).startswith("skipped_upstream:")


def _skipped(stage: str) -> dict[str, Any]:
    return {"status_code": 0, "latency_ms": 0.0, "body": None, "error": f"skipped_upstream:{stage}"}


def _summarise_raw_runs(raw_runs: list[dict]) -> dict[str, dict[str, Any]]:
    endpoint_latencies = {name: [] for name in ENDPOINT_NAMES}
    endpoint_errors = {name: 0 for name in ENDPOINT_NAMES}
    endpoint_applicable = {name: 0 for name in ENDPOINT_NAMES}
    endpoint_skipped = {name: 0 for name in ENDPOINT_NAMES}

    for run in raw_runs:
        timings = run.get("timings", {})
        if not isinstance(timings, dict):
            continue
        for endpoint, result in timings.items():
            if endpoint not in endpoint_latencies:
                continue
            if _is_skipped_result(result):
                endpoint_skipped[endpoint] += 1
                continue
            endpoint_applicable[endpoint] += 1
            if not isinstance(result, dict) or result.get("error") or result.get("status_code", 200) >= 400:
                endpoint_errors[endpoint] += 1
            else:
                endpoint_latencies[endpoint].append(result.get("latency_ms", 0.0))

    summary = {}
    for endpoint in ENDPOINT_NAMES:
        summary[endpoint] = {
            "p50_ms": compute_percentile(endpoint_latencies[endpoint], 50),
            "p95_ms": compute_percentile(endpoint_latencies[endpoint], 95),
            "error_rate_pct": round(
                endpoint_errors[endpoint] / endpoint_applicable[endpoint] * 100, 1
            )
            if endpoint_applicable[endpoint] > 0
            else 0.0,
            "sample_count": len(endpoint_latencies[endpoint]),
            "applicable_count": endpoint_applicable[endpoint],
            "skipped_count": endpoint_skipped[endpoint],
        }
    return summary


def run_scenario_perf(
    base_url: str,
    scenario: dict,
    auth_headers: dict[str, str],
) -> dict[str, dict]:
    with httpx.Client() as client:
        timings = {}

        timings["refine_learning_goal"] = timed_post(
            client,
            f"{base_url}/refine-learning-goal",
            _base_payload(
                {
                    "learning_goal": scenario["learning_goal"],
                    "learner_information": _api_learner_info(scenario),
                }
            ),
            headers=auth_headers,
            timeout=60.0,
        )

        timings["identify_skill_gap"] = timed_post(
            client,
            f"{base_url}/identify-skill-gap-with-info",
            _base_payload(
                {
                    "learning_goal": scenario["learning_goal"],
                    "learner_information": _api_learner_info(scenario),
                }
            ),
            headers=auth_headers,
            timeout=90.0,
        )
        sg_result = timings["identify_skill_gap"]
        if sg_result.get("error") or sg_result.get("status_code", 200) >= 400:
            timings["create_learner_profile"] = _skipped("identify_skill_gap")
            timings["schedule_learning_path"] = _skipped("create_learner_profile")
            timings["generate_learning_content"] = _skipped("schedule_learning_path")
            timings["chat_with_tutor"] = _skipped("create_learner_profile")
            return timings

        sg_body = sg_result.get("body") or {}
        timings["create_learner_profile"] = timed_post(
            client,
            f"{base_url}/create-learner-profile-with-info",
            _base_payload(
                {
                    "learning_goal": scenario["learning_goal"],
                    "learner_information": _api_learner_info(scenario),
                    "skill_gaps": json.dumps(sg_body.get("skill_gaps", [])),
                }
            ),
            headers=auth_headers,
            timeout=90.0,
        )
        profile_result = timings["create_learner_profile"]
        if profile_result.get("error") or profile_result.get("status_code", 200) >= 400:
            timings["schedule_learning_path"] = _skipped("create_learner_profile")
            timings["generate_learning_content"] = _skipped("schedule_learning_path")
            timings["chat_with_tutor"] = _skipped("create_learner_profile")
            return timings

        profile_body = _unwrap_profile_body(profile_result.get("body") or {})
        timings["schedule_learning_path"] = timed_post(
            client,
            f"{base_url}/schedule-learning-path",
            _base_payload(
                {
                    "learner_profile": json.dumps(profile_body),
                    "session_count": DEFAULT_SESSION_COUNT,
                }
            ),
            headers=auth_headers,
            timeout=90.0,
        )
        path_result = timings["schedule_learning_path"]
        if path_result.get("error") or path_result.get("status_code", 200) >= 400:
            timings["generate_learning_content"] = _skipped("schedule_learning_path")
            timings["chat_with_tutor"] = _skipped("schedule_learning_path")
            return timings

        path_body = path_result.get("body") or {}
        first_session = (path_body.get("learning_path") or [{}])[0]
        timings["generate_learning_content"] = timed_post(
            client,
            f"{base_url}/generate-learning-content",
            _base_payload(
                {
                    "learner_profile": json.dumps(profile_body),
                    "learning_path": json.dumps(path_body),
                    "learning_session": json.dumps(first_session),
                    "use_search": True,
                    "allow_parallel": True,
                    "with_quiz": True,
                }
            ),
            headers=auth_headers,
            timeout=240.0,
        )
        content_result = timings["generate_learning_content"]
        if content_result.get("error") or content_result.get("status_code", 200) >= 400:
            timings["chat_with_tutor"] = _skipped("generate_learning_content")
            return timings

        timings["chat_with_tutor"] = timed_post(
            client,
            f"{base_url}/chat-with-tutor",
            _base_payload(
                {
                    "messages": json.dumps([{"role": "user", "content": "What should I focus on first?"}]),
                    "learner_profile": json.dumps(profile_body),
                    "return_metadata": True,
                    "allow_preference_updates": False,
                }
            ),
            headers=auth_headers,
            timeout=60.0,
        )
        return timings


def run_eval_api_perf(
    scenarios: list[dict],
    cache_path: str | None = None,
    resume: bool = False,
    *,
    base_url: str = BETA_BASE_URL,
) -> dict:
    print(f"\n=== API Perf: {VERSION_LABEL} ===")
    auth_headers = bootstrap_auth_headers(base_url)
    existing = _load_perf_cache(cache_path) if (resume and cache_path) else {}
    scenario_ids = {scenario["id"] for scenario in scenarios}
    raw_runs = []
    completed_ids = set()

    for run in existing.get(VERSION_KEY, {}).get("raw_runs", []):
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
            timings = run_scenario_perf(base_url, scenario, auth_headers)
            raw_runs.append({"scenario_id": sid, "timings": timings})
        except Exception as exc:
            raw_runs.append({"scenario_id": sid, "error": str(exc)})
        if cache_path:
            _save_perf_cache(
                cache_path,
                {
                    VERSION_KEY: {
                        "label": VERSION_LABEL,
                        "raw_runs": raw_runs,
                        "summary": _summarise_raw_runs(raw_runs),
                    }
                },
            )

    return {
        VERSION_KEY: {
            "label": VERSION_LABEL,
            "raw_runs": raw_runs,
            "summary": _summarise_raw_runs(raw_runs),
        }
    }


if __name__ == "__main__":
    with open(os.path.join(DATASETS_DIR, "shared_test_cases.json")) as file:
        dataset = json.load(file)

    out = run_eval_api_perf(
        dataset["scenarios"],
        cache_path=os.path.join(RESULTS_DIR, "api_perf_checkpoint.json"),
    )
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "api_perf_results.json")
    with open(out_path, "w") as file:
        json.dump(out, file, indent=2)

    print("\n=== API Performance Summary ===")
    for endpoint, values in out[VERSION_KEY]["summary"].items():
        print(f"  {endpoint}: p50={values['p50_ms']}ms p95={values['p95_ms']}ms error={values['error_rate_pct']}%")
    print(f"\nFull results saved to {out_path}")
