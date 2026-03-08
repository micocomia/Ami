"""Adaptation pipeline: detect preference/mastery changes and adapt the learning path."""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from modules.learner_profiler.utils import fslsm_adaptation
from modules.learning_plan_generator.utils.plan_regeneration import (
    RegenerationDecision,
    compute_fslsm_deltas,
    decide_regeneration,
)


def _parse_iso_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value).timestamp()
        return float(value)
    except Exception:
        return None


def run_adaptation(
    llm: Any,
    goal_id: int,
    goal: Dict[str, Any],
    effective_profile: Dict[str, Any],
    adaptation_state: Dict[str, Any],
    snapshot_profile: Optional[Dict[str, Any]],
    mode: str,
    force: bool,
    cooldown_secs: int,
    mastery_threshold_default: float,
    hysteresis: float,
    patch_goal_fn: Callable[[str, int, Dict[str, Any]], Any],
    delete_profile_snapshot_fn: Callable[[str, int], None],
    reschedule_fn: Callable,
    schedule_agentic_fn: Callable,
    stitch_fn: Callable,
    evaluate_plan_fn: Callable,
    ctx: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Core adaptation logic: trigger detection, fingerprinting, cooldown checks, plan update.

    Store writes (patch_goal, delete_profile_snapshot) are performed via the passed callables.
    ctx["fingerprint"] is set as soon as the fingerprint is computed, allowing the caller's
    exception handler to record failures even if an error occurs afterward.

    Returns the full API response payload dict.
    """
    old_profile = snapshot_profile or effective_profile
    old_fslsm = fslsm_adaptation.extract_fslsm_dims(old_profile)
    new_fslsm = fslsm_adaptation.extract_fslsm_dims(effective_profile)

    current_plan = {"learning_path": goal.get("learning_path", [])}
    mastery_results = fslsm_adaptation.build_mastery_results_for_plan(
        current_plan.get("learning_path", []),
        mastery_threshold_default=mastery_threshold_default,
    )

    prev_band_state = adaptation_state.get("last_band_state_by_dim", {})
    if not isinstance(prev_band_state, dict):
        prev_band_state = {}

    if isinstance(snapshot_profile, dict):
        old_band_state = fslsm_adaptation.compute_band_state(old_fslsm, prev_band_state, hysteresis=hysteresis)
        current_band_state = fslsm_adaptation.compute_band_state(new_fslsm, old_band_state, hysteresis=hysteresis)
        changed_dims = [
            dim for dim in fslsm_adaptation.FSLSM_DIM_KEYS
            if old_band_state.get(dim) and old_band_state.get(dim) != current_band_state.get(dim)
        ]
    else:
        current_band_state = fslsm_adaptation.compute_band_state(new_fslsm, prev_band_state, hysteresis=hysteresis)
        changed_dims = [
            dim for dim in fslsm_adaptation.FSLSM_DIM_KEYS
            if prev_band_state.get(dim) and prev_band_state.get(dim) != current_band_state.get(dim)
        ]

    trigger_sources: List[str] = []
    if fslsm_adaptation.any_severe_mastery_failure(mastery_results, mastery_threshold_default=mastery_threshold_default):
        trigger_sources.append("mastery")
    if changed_dims:
        trigger_sources.append("preference_band_transition")
    if force:
        trigger_sources.append("force")

    fingerprint = fslsm_adaptation.build_adaptation_fingerprint(
        goal_id=goal_id,
        band_state_by_dim=current_band_state,
        evidence_windows=adaptation_state.get("evidence_windows", {}),
        mode=mode,
        path_version=fslsm_adaptation.path_version_hash(goal),
    )
    ctx["fingerprint"] = fingerprint

    # Duplicate fingerprint — nothing changed
    if not force and adaptation_state.get("last_applied_fingerprint") == fingerprint:
        adaptation_state["last_result"] = "noop"
        adaptation_state["last_reason"] = "Duplicate adaptation fingerprint."
        adaptation_state["last_band_state_by_dim"] = current_band_state
        patch_goal_fn(user_id, goal_id, {"adaptation_state": adaptation_state})
        return {
            **current_plan,
            "agent_metadata": {},
            "adaptation": {
                "status": "noop_duplicate",
                "applied": False,
                "reason": adaptation_state["last_reason"],
                "trigger_sources": trigger_sources,
                "fingerprint": fingerprint,
                "cooldown_remaining_secs": 0,
            },
        }

    # Cooldown — recent failure for same fingerprint
    if not force and adaptation_state.get("last_failed_fingerprint") == fingerprint:
        failed_at = _parse_iso_ts(adaptation_state.get("last_failed_at"))
        now_ts = datetime.now(timezone.utc).timestamp()
        if failed_at is not None and now_ts - failed_at < cooldown_secs:
            remaining = int(cooldown_secs - (now_ts - failed_at))
            return {
                **current_plan,
                "agent_metadata": {},
                "adaptation": {
                    "status": "cooldown",
                    "applied": False,
                    "reason": "Recent adaptation failure is in cooldown.",
                    "trigger_sources": trigger_sources,
                    "fingerprint": fingerprint,
                    "cooldown_remaining_secs": max(remaining, 0),
                },
            }

    # No triggers — record and clear snapshot
    if not trigger_sources:
        adaptation_state["last_applied_fingerprint"] = fingerprint
        adaptation_state["last_result"] = "noop"
        adaptation_state["last_reason"] = "No adaptation trigger sources detected."
        adaptation_state["last_band_state_by_dim"] = current_band_state
        adaptation_state["snapshot_saved_at"] = None
        patch_goal_fn(user_id, goal_id, {"adaptation_state": adaptation_state})
        delete_profile_snapshot_fn(user_id, goal_id)
        return {
            **current_plan,
            "agent_metadata": {},
            "adaptation": {
                "status": "noop",
                "applied": False,
                "reason": adaptation_state["last_reason"],
                "trigger_sources": [],
                "fingerprint": fingerprint,
                "cooldown_remaining_secs": 0,
            },
        }

    # Decide and execute plan changes
    decision = decide_regeneration(current_plan, old_fslsm, new_fslsm, mastery_results)
    if decision.action == "keep" and ("preference_band_transition" in trigger_sources or force):
        future_indices = [
            i for i, session in enumerate(current_plan.get("learning_path", []))
            if not bool((session or {}).get("if_learned", False))
        ]
        decision = RegenerationDecision(
            action="adjust_future",
            reason="FSLSM band transition detected. Adjusting future sessions.",
            affected_sessions=future_indices,
        )

    result_plan = current_plan
    agent_metadata = {
        "decision": decision.model_dump(),
        "fslsm_deltas": compute_fslsm_deltas(old_fslsm, new_fslsm),
        "mastery_results": mastery_results,
        "trigger_sources": trigger_sources,
        "changed_band_dimensions": changed_dims,
    }

    if decision.action == "adjust_future":
        result_plan = reschedule_fn(
            llm,
            current_plan.get("learning_path", []),
            effective_profile,
            other_feedback=f"Adaptation reason: {decision.reason}",
        )
    elif decision.action == "regenerate":
        plan, regen_metadata = schedule_agentic_fn(llm, effective_profile)
        result_plan = stitch_fn(current_plan, plan)
        agent_metadata.update(regen_metadata)

    sim_feedback = evaluate_plan_fn(llm, result_plan, effective_profile)
    agent_metadata["evaluation_feedback"] = sim_feedback
    if not isinstance(sim_feedback, dict):
        sim_feedback = {}
    agent_metadata["evaluation"] = {
        "pass": sim_feedback.get("is_acceptable", True),
        "issues": sim_feedback.get("issues", []),
        "feedback_summary": sim_feedback.get("feedback", {}),
    }

    adaptation_state["last_applied_fingerprint"] = fingerprint
    adaptation_state["last_result"] = "applied"
    adaptation_state["last_reason"] = decision.reason
    adaptation_state["last_band_state_by_dim"] = current_band_state
    adaptation_state["snapshot_saved_at"] = None
    adaptation_state["last_failed_fingerprint"] = None
    adaptation_state["last_failed_at"] = None

    patch_goal_fn(
        user_id,
        goal_id,
        {
            "learning_path": result_plan.get("learning_path", []),
            "plan_agent_metadata": agent_metadata,
            "adaptation_state": adaptation_state,
        },
    )
    delete_profile_snapshot_fn(user_id, goal_id)

    return {
        **result_plan,
        "agent_metadata": agent_metadata,
        "adaptation": {
            "status": "applied",
            "applied": True,
            "reason": decision.reason,
            "trigger_sources": trigger_sources,
            "fingerprint": fingerprint,
            "cooldown_remaining_secs": 0,
        },
    }
