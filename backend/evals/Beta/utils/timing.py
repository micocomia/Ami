"""Request timing utilities for Beta API performance evaluation."""

import time
from typing import Any

import httpx


def timed_post(
    client: httpx.Client,
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        response = client.post(url, json=payload, headers=headers, timeout=timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        return {
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 1),
            "body": body,
            "error": None,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status_code": 0,
            "latency_ms": round(latency_ms, 1),
            "body": None,
            "error": str(exc),
        }


def compute_percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * percentile / 100) - 1)
    return round(sorted_vals[idx], 1)
