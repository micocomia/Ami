"""Deterministic FSLSM adaptation policy helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


FSLSM_DIM_KEYS: Tuple[str, ...] = (
    "fslsm_processing",
    "fslsm_perception",
    "fslsm_input",
    "fslsm_understanding",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value).timestamp()
        return float(value)
    except Exception:
        return None


def _iso_from_ts(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def default_adaptation_state() -> Dict[str, Any]:
    return {
        "last_applied_fingerprint": None,
        "last_failed_fingerprint": None,
        "last_failed_at": None,
        "last_result": None,
        "last_reason": None,
        "evidence_windows": {},
        "daily_movement_budget": {},
        "last_band_state_by_dim": {},
        "snapshot_saved_at": None,
        "updated_at": _now_iso(),
    }


def normalize_adaptation_state(goal: Dict[str, Any]) -> Dict[str, Any]:
    state = copy.deepcopy((goal or {}).get("adaptation_state", {}))
    if not isinstance(state, dict):
        state = {}
    defaults = default_adaptation_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
    if not isinstance(state.get("evidence_windows"), dict):
        state["evidence_windows"] = {}
    if not isinstance(state.get("daily_movement_budget"), dict):
        state["daily_movement_budget"] = {}
    if not isinstance(state.get("last_band_state_by_dim"), dict):
        state["last_band_state_by_dim"] = {}
    state["updated_at"] = _now_iso()
    return state


def extract_fslsm_dims(profile: Dict[str, Any]) -> Dict[str, float]:
    dims = (
        (profile or {})
        .get("learning_preferences", {})
        .get("fslsm_dimensions", {})
    )
    result: Dict[str, float] = {}
    for key in FSLSM_DIM_KEYS:
        try:
            result[key] = float((dims or {}).get(key, 0.0) or 0.0)
        except Exception:
            result[key] = 0.0
    return result


def path_version_hash(goal: Dict[str, Any]) -> str:
    payload = goal.get("learning_path", []) if isinstance(goal, dict) else []
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _band_with_hysteresis(value: float, prev_band: Optional[str], hysteresis: float = 0.02) -> str:
    low_hold = 0.7 - hysteresis
    high_enter = 0.7 + hysteresis
    mid_pos_hold = 0.3 - hysteresis
    mid_pos_enter = 0.3 + hysteresis
    mid_neg_hold = -0.3 + hysteresis
    mid_neg_enter = -0.3 - hysteresis
    low_enter = -0.7 - hysteresis
    low_release = -0.7 + hysteresis
    if prev_band == "strong_positive" and value >= low_hold:
        return "strong_positive"
    if prev_band == "mild_positive" and mid_pos_hold <= value < high_enter:
        return "mild_positive"
    if prev_band == "neutral" and mid_neg_enter < value < mid_pos_enter:
        return "neutral"
    if prev_band == "mild_negative" and low_release < value <= mid_neg_hold:
        return "mild_negative"
    if prev_band == "strong_negative" and value <= low_release:
        return "strong_negative"

    if value >= high_enter:
        return "strong_positive"
    if value >= mid_pos_enter:
        return "mild_positive"
    if value > mid_neg_enter:
        return "neutral"
    if value > low_enter:
        return "mild_negative"
    return "strong_negative"


def compute_band_state(
    dims: Dict[str, float],
    prev_band_state: Optional[Dict[str, str]] = None,
    hysteresis: float = 0.02,
) -> Dict[str, str]:
    prev_band_state = prev_band_state or {}
    result: Dict[str, str] = {}
    for key in FSLSM_DIM_KEYS:
        result[key] = _band_with_hysteresis(float(dims.get(key, 0.0)), prev_band_state.get(key), hysteresis=hysteresis)
    return result


def build_mastery_results_for_plan(
    learning_path: List[Dict[str, Any]],
    mastery_threshold_default: float = 70.0,
) -> List[Dict[str, Any]]:
    mastery_results = []
    for i, session in enumerate(learning_path):
        if not isinstance(session, dict):
            continue
        if session.get("mastery_score") is None:
            continue
        threshold = float(session.get("mastery_threshold", mastery_threshold_default) or mastery_threshold_default)
        score = float(session.get("mastery_score", 0) or 0)
        mastery_results.append({
            "session_index": i,
            "session_id": session.get("id", ""),
            "score": score,
            "is_mastered": bool(session.get("is_mastered", False)),
            "threshold": threshold,
        })
    return mastery_results


def any_severe_mastery_failure(
    mastery_results: List[Dict[str, Any]],
    mastery_threshold_default: float = 70.0,
) -> bool:
    for result in mastery_results:
        threshold = float(result.get("threshold", mastery_threshold_default) or mastery_threshold_default)
        score = float(result.get("score", 0) or 0)
        if (not bool(result.get("is_mastered", False))) and score < threshold * 0.8:
            return True
    return False


def _evidence_signature(evidence_windows: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    signature: Dict[str, Dict[str, int]] = {}
    for key in sorted((evidence_windows or {}).keys()):
        events = evidence_windows.get(key, [])
        if not isinstance(events, list):
            continue
        recent = [evt for evt in events[-3:] if isinstance(evt, dict)]
        signature[key] = {
            "total": len(events),
            "severe_last3": sum(1 for evt in recent if bool(evt.get("severe_failure"))),
            "success_last3": sum(1 for evt in recent if bool(evt.get("strong_success"))),
        }
    return signature


def build_adaptation_fingerprint(
    *,
    goal_id: int,
    band_state_by_dim: Dict[str, str],
    evidence_windows: Dict[str, Any],
    mode: str,
    path_version: str,
) -> str:
    fingerprint_payload = {
        "goal_id": goal_id,
        "band_state_by_dim": band_state_by_dim,
        "evidence_signature_by_key": _evidence_signature(evidence_windows),
        "mode": mode,
        "path_version": path_version,
    }
    payload = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _infer_input_mode_fallback(
    session: Dict[str, Any],
    learning_content: Optional[Dict[str, Any]],
    threshold_diff: int = 2,
) -> str:
    hint = str((session or {}).get("input_mode_hint", "mixed")).strip().lower()
    if hint in {"visual", "verbal"}:
        return hint
    if hint not in {"visual", "verbal", "mixed"}:
        hint = "mixed"

    visual_keywords = ("module map", "diagram", "chart", "visual", "figure", "image", "video")
    verbal_keywords = ("explain", "discussion", "reading", "narrative", "text-based", "lecture")
    visual_score = 0
    verbal_score = 0

    session_text = " ".join(
        str((session or {}).get(k, "") or "")
        for k in ("title", "abstract", "session_sequence_hint")
    ).lower()
    for word in visual_keywords:
        visual_score += session_text.count(word)
    for word in verbal_keywords:
        verbal_score += session_text.count(word)

    if isinstance(learning_content, dict):
        doc = learning_content.get("document")
        if isinstance(doc, dict):
            markdown = str(doc.get("markdown", "") or "")
            lower = markdown.lower()
            visual_score += lower.count("![")
            visual_score += lower.count("```mermaid")
            visual_score += lower.count("video")
            visual_score += lower.count("diagram")
            verbal_score += lower.count("explain")
            verbal_score += lower.count("discussion")
            verbal_score += lower.count("narrative")
            non_code = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
            prose_words = len(re.findall(r"[A-Za-z']+", non_code))
            if prose_words >= 180:
                verbal_score += 1
            media = doc.get("asset_urls", [])
            if isinstance(media, list):
                visual_score += min(len(media), 2)

    if visual_score - verbal_score >= threshold_diff:
        return "visual"
    if verbal_score - visual_score >= threshold_diff:
        return "verbal"
    return "mixed"


def session_signal_keys(
    session: Dict[str, Any],
    learning_content: Optional[Dict[str, Any]] = None,
) -> List[str]:
    keys: List[str] = []
    if bool((session or {}).get("has_checkpoint_challenges", False)):
        keys.append("fslsm_processing:negative")
    elif int((session or {}).get("thinking_time_buffer_minutes", 0) or 0) >= 5:
        keys.append("fslsm_processing:positive")

    seq_hint = str((session or {}).get("session_sequence_hint", "") or "").strip().lower()
    if seq_hint == "application-first":
        keys.append("fslsm_perception:negative")
    elif seq_hint == "theory-first":
        keys.append("fslsm_perception:positive")

    nav_mode = str((session or {}).get("navigation_mode", "linear") or "linear").strip().lower()
    if nav_mode == "linear":
        keys.append("fslsm_understanding:negative")
    elif nav_mode == "free":
        keys.append("fslsm_understanding:positive")

    input_mode = _infer_input_mode_fallback(session, learning_content, threshold_diff=2)
    if input_mode == "visual":
        keys.append("fslsm_input:negative")
    elif input_mode == "verbal":
        keys.append("fslsm_input:positive")
    return keys


def append_evidence(
    evidence_windows: Dict[str, Any],
    key: str,
    *,
    severe_failure: bool,
    strong_success: bool,
    window_size: int = 3,
) -> None:
    events = evidence_windows.setdefault(key, [])
    if not isinstance(events, list):
        events = []
        evidence_windows[key] = events
    events.append({
        "severe_failure": bool(severe_failure),
        "strong_success": bool(strong_success),
    })
    evidence_windows[key] = events[-window_size:]


def _apply_daily_cap(
    adaptation_state: Dict[str, Any],
    dim_key: str,
    delta: float,
    *,
    daily_cap: float = 0.20,
) -> float:
    if abs(delta) < 1e-9:
        return 0.0
    budget = adaptation_state.setdefault("daily_movement_budget", {}).setdefault(dim_key, {})
    now_ts = datetime.now(timezone.utc).timestamp()
    window_start = _parse_iso_ts(budget.get("window_start"))
    moved = float(budget.get("moved", 0.0) or 0.0)
    if window_start is None or now_ts - window_start > 24 * 60 * 60:
        window_start = now_ts
        moved = 0.0
    remaining = max(0.0, daily_cap - moved)
    if remaining <= 1e-9:
        applied = 0.0
    else:
        applied = max(-remaining, min(remaining, delta))
    moved += abs(applied)
    budget["window_start"] = _iso_from_ts(window_start)
    budget["moved"] = round(moved, 6)
    return applied


def update_fslsm_from_evidence(
    profile: Dict[str, Any],
    adaptation_state: Dict[str, Any],
    *,
    daily_cap: float = 0.20,
) -> Tuple[Dict[str, Any], Dict[str, float]]:
    updated = copy.deepcopy(profile or {})
    prefs = updated.setdefault("learning_preferences", {})
    dims = prefs.setdefault("fslsm_dimensions", {})
    current_dims = extract_fslsm_dims(updated)
    net_changes: Dict[str, float] = {key: 0.0 for key in FSLSM_DIM_KEYS}
    windows = adaptation_state.get("evidence_windows", {})
    if not isinstance(windows, dict):
        return updated, net_changes

    proposed_by_dim: Dict[str, float] = {key: 0.0 for key in FSLSM_DIM_KEYS}
    for key, events in windows.items():
        if not isinstance(events, list):
            continue
        recent = [evt for evt in events[-3:] if isinstance(evt, dict)]
        if len(recent) < 3:
            continue
        severe_count = sum(1 for evt in recent if bool(evt.get("severe_failure")))
        success_count = sum(1 for evt in recent if bool(evt.get("strong_success")))
        try:
            dim_key, sign = key.split(":", 1)
        except ValueError:
            continue
        if dim_key not in FSLSM_DIM_KEYS:
            continue
        if severe_count >= 2:
            proposed_by_dim[dim_key] += -0.10 if sign == "positive" else 0.10
            continue
        if success_count >= 2:
            proposed_by_dim[dim_key] += 0.05 if sign == "positive" else -0.05

    for dim_key, proposed_delta in proposed_by_dim.items():
        if abs(proposed_delta) < 1e-9:
            continue
        applied_delta = _apply_daily_cap(adaptation_state, dim_key, proposed_delta, daily_cap=daily_cap)
        if abs(applied_delta) < 1e-9:
            continue
        new_val = max(-1.0, min(1.0, current_dims.get(dim_key, 0.0) + applied_delta))
        current_dims[dim_key] = new_val
        net_changes[dim_key] = round(applied_delta, 6)

    for key in FSLSM_DIM_KEYS:
        dims[key] = round(float(current_dims.get(key, 0.0)), 6)
    return updated, net_changes


def build_adaptation_signal(
    goal: Dict[str, Any],
    profile: Dict[str, Any],
    adaptation_state: Dict[str, Any],
    *,
    mastery_threshold_default: float = 70.0,
    snapshot_profile: Optional[Dict[str, Any]] = None,
    hysteresis: float = 0.02,
) -> Tuple[bool, Optional[str], List[str], Dict[str, str]]:
    learning_path = goal.get("learning_path", []) if isinstance(goal, dict) else []
    mastery_results = build_mastery_results_for_plan(
        learning_path if isinstance(learning_path, list) else [],
        mastery_threshold_default=mastery_threshold_default,
    )
    has_mastery_failure = any_severe_mastery_failure(
        mastery_results,
        mastery_threshold_default=mastery_threshold_default,
    )
    prev_band_state = adaptation_state.get("last_band_state_by_dim", {})
    if not isinstance(prev_band_state, dict):
        prev_band_state = {}
    if isinstance(snapshot_profile, dict):
        snapshot_bands = compute_band_state(extract_fslsm_dims(snapshot_profile), prev_band_state, hysteresis=hysteresis)
        current_band_state = compute_band_state(extract_fslsm_dims(profile), snapshot_bands, hysteresis=hysteresis)
        changed_dims = [
            dim for dim in FSLSM_DIM_KEYS
            if snapshot_bands.get(dim) and snapshot_bands.get(dim) != current_band_state.get(dim)
        ]
    else:
        current_band_state = compute_band_state(extract_fslsm_dims(profile), prev_band_state, hysteresis=hysteresis)
        changed_dims = [
            dim for dim in FSLSM_DIM_KEYS
            if prev_band_state.get(dim) and prev_band_state.get(dim) != current_band_state.get(dim)
        ]
    sources: List[str] = []
    if has_mastery_failure:
        sources.append("mastery")
    if changed_dims:
        sources.append("preference_band_transition")
    if not sources:
        return False, None, [], current_band_state
    if "mastery" in sources and "preference_band_transition" in sources:
        message = "Recent performance and profile shifts suggest future sessions should be adapted."
    elif "mastery" in sources:
        message = "Recent quiz performance suggests future sessions may need adjustment."
    else:
        message = "Profile shifts crossed adaptation bands; future sessions may need adjustment."
    return True, message, sources, current_band_state
