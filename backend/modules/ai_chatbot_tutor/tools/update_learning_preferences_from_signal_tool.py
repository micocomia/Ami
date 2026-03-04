from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Literal

from base import BaseAgent
from base.llm_factory import LLMFactory
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator


_FSLSM_SIGNAL_CLASSIFIER_SYSTEM_PROMPT = """
You are an FSLSM preference signal classifier.

Task:
- Read one learner message.
- Detect only strong, explicit, durable preference signals.
- Ignore weak, transient, or ambiguous requests.
- Treat explicit profile-correction statements as strong updates.
  Example: "my input vector is wrong; I should be a verbal learner".

FSLSM mapping:
- processing:negative = active/hands-on preference
- processing:positive = reflective/observation preference
- perception:negative = concrete/example-first preference
- perception:positive = conceptual/theory-first preference
- input:negative = visual preference
- input:positive = verbal/text preference
- understanding:negative = sequential/step-by-step preference
- understanding:positive = global/big-picture-first preference

Output format:
- Return JSON only with shape: {"signals":[...]}.
- Each signal item must include:
  - dimension: one of processing|perception|input|understanding
  - direction: one of positive|negative
  - confidence: float between 0 and 1
  - evidence: short grounded phrase from the user message
- If no strong signal exists, return {"signals":[]}.

Confidence policy:
- Strong explicit first-person corrections/preferences should usually be >= 0.7.
- Hedging words (e.g., "I think", "maybe") should not lower confidence when the user still makes
  a direct correction such as "I should be a verbal learner" or "I prefer step-by-step".
""".strip()

_FSLSM_SIGNAL_CLASSIFIER_TASK_PROMPT = """
Classify strong FSLSM preference signals in this learner message:
{latest_user_message}
""".strip()


class UpdateLearningPreferencesFromSignalInput(BaseModel):
    latest_user_message: str = Field(..., description="Latest user utterance.")
    user_id: Optional[str] = Field(default=None, description="User ID for persistence.")
    goal_id: Optional[int] = Field(default=None, description="Goal ID for persistence.")
    learner_information: Optional[str] = Field(default="", description="Optional learner information context.")


class _FSLSMSignalItem(BaseModel):
    dimension: Literal["processing", "perception", "input", "understanding"]
    direction: Literal["positive", "negative"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = ""

    @field_validator("dimension", mode="before")
    @classmethod
    def _normalize_dimension(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, value: Any) -> str:
        return str(value or "").strip().lower()

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> float:
        return float(value)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, value: Any) -> str:
        return str(value or "").strip()


class _FSLSMSignalBatch(BaseModel):
    signals: List[_FSLSMSignalItem] = Field(default_factory=list)


class _FSLSMSignalClassifier(BaseAgent):
    name: str = "FSLSMSignalClassifier"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=_FSLSM_SIGNAL_CLASSIFIER_SYSTEM_PROMPT,
            tools=None,
            jsonalize_output=True,
        )

    def classify(self, latest_user_message: str) -> _FSLSMSignalBatch:
        raw_output = self.invoke(
            {"latest_user_message": str(latest_user_message or "")},
            task_prompt=_FSLSM_SIGNAL_CLASSIFIER_TASK_PROMPT,
        )
        return _FSLSMSignalBatch.model_validate(raw_output)


def _normalize_confidence_threshold(value: Any) -> float:
    try:
        threshold = float(value)
    except Exception:
        return 0.6
    if threshold < 0.0:
        return 0.0
    if threshold > 1.0:
        return 1.0
    return threshold


def _classify_preference_signals_with_llm(
    latest_user_message: str,
    llm: Any,
    *,
    confidence_threshold: float,
) -> Dict[str, List[str]]:
    classifier = _FSLSMSignalClassifier(llm)
    batch = classifier.classify(latest_user_message)
    threshold = _normalize_confidence_threshold(confidence_threshold)

    per_key: Dict[str, List[str]] = {}
    for item in batch.signals:
        if float(item.confidence) < threshold:
            continue
        key = f"fslsm_{item.dimension}:{item.direction}"
        evidence = item.evidence or f"llm:{item.dimension}:{item.direction}"
        evidence_items = per_key.setdefault(key, [])
        if evidence not in evidence_items:
            evidence_items.append(evidence)
    return per_key


def create_update_learning_preferences_from_signal_tool(
    *,
    safe_update_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    sink: Optional[Dict[str, Any]] = None,
    signal_classifier_llm: Optional[Any] = None,
    signal_confidence_threshold: float = 0.6,
):
    resolved_signal_classifier_llm = signal_classifier_llm
    classifier_init_error: Optional[str] = None
    classifier_init_attempted = False

    @tool("update_learning_preferences_from_signal", args_schema=UpdateLearningPreferencesFromSignalInput)
    def update_learning_preferences_from_signal(
        latest_user_message: str,
        user_id: Optional[str] = None,
        goal_id: Optional[int] = None,
        learner_information: Optional[str] = "",
    ) -> str:
        """Persist preference updates only when strong interaction signals are present."""
        nonlocal resolved_signal_classifier_llm
        nonlocal classifier_init_attempted
        nonlocal classifier_init_error

        threshold = _normalize_confidence_threshold(signal_confidence_threshold)
        if resolved_signal_classifier_llm is None and not classifier_init_attempted:
            classifier_init_attempted = True
            try:
                resolved_signal_classifier_llm = LLMFactory.create(
                    model="gpt-4o-mini",
                    model_provider="openai",
                    temperature=0,
                )
                classifier_init_error = None
            except Exception as exc:
                classifier_init_error = str(exc)
                resolved_signal_classifier_llm = None

        if resolved_signal_classifier_llm is None:
            reason = "Preference signal classifier is unavailable."
            if classifier_init_error:
                reason = f"{reason} {classifier_init_error}"
            return json.dumps({
                "profile_updated": False,
                "reason": reason,
                "signals": {},
            })

        try:
            signals = _classify_preference_signals_with_llm(
                latest_user_message,
                resolved_signal_classifier_llm,
                confidence_threshold=threshold,
            )
        except Exception as exc:
            return json.dumps({
                "profile_updated": False,
                "reason": f"Preference signal classification failed: {exc}",
                "signals": {},
            })

        if not signals:
            return json.dumps({
                "profile_updated": False,
                "reason": f"No strong preference signal detected at confidence >= {threshold:.2f}.",
                "signals": {},
            })

        if not user_id or goal_id is None:
            return json.dumps({
                "profile_updated": False,
                "reason": "Missing user or goal context; cannot persist profile update.",
                "signals": signals,
            })

        if safe_update_fn is None:
            return json.dumps({
                "profile_updated": False,
                "reason": "Preference update function is unavailable.",
                "signals": signals,
            })

        try:
            result = safe_update_fn(
                user_id=user_id,
                goal_id=int(goal_id),
                latest_user_message=latest_user_message,
                learner_information=learner_information or "",
                signals=signals,
            ) or {}
        except Exception as exc:
            return json.dumps({
                "profile_updated": False,
                "reason": f"Preference update failed: {exc}",
                "signals": signals,
            })

        profile_updated = bool(result.get("profile_updated", False))
        updated_profile = result.get("updated_learner_profile")
        if sink is not None and profile_updated and isinstance(updated_profile, Mapping):
            sink["profile_updated"] = True
            sink["updated_learner_profile"] = dict(updated_profile)
            sink["signals"] = signals

        payload = {
            "profile_updated": profile_updated,
            "signals": signals,
            "reason": result.get("reason", "Updated from strong preference signal." if profile_updated else "No update applied."),
        }
        return json.dumps(payload, ensure_ascii=False)

    return update_learning_preferences_from_signal


__all__ = [
    "UpdateLearningPreferencesFromSignalInput",
    "create_update_learning_preferences_from_signal_tool",
]
