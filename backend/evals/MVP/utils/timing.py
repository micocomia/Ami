"""
Request timing utilities for API performance evaluation.
"""

import time
from typing import Any
import httpx


def timed_post(client: httpx.Client, url: str, payload: dict) -> dict[str, Any]:
    """
    POST to url with payload, returning the response body plus timing metadata.
    Returns:
        {
            "status_code": int,
            "latency_ms": float,
            "body": dict | None,
            "error": str | None
        }
    """
    start = time.perf_counter()
    try:
        resp = client.post(url, json=payload, timeout=120.0)
        latency_ms = (time.perf_counter() - start) * 1000
        body = None
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {
            "status_code": resp.status_code,
            "latency_ms": round(latency_ms, 1),
            "body": body,
            "error": None,
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status_code": 0,
            "latency_ms": round(latency_ms, 1),
            "body": None,
            "error": str(e),
        }


def compute_percentile(values: list[float], p: int) -> float:
    """Compute the p-th percentile of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * p / 100) - 1)
    return round(sorted_vals[idx], 1)
