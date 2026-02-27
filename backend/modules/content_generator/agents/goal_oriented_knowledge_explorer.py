from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any, Mapping

from pydantic import BaseModel, field_validator, ValidationError

from base import BaseAgent
from modules.content_generator.prompts.goal_oriented_knowledge_explorer import (
    goal_oriented_knowledge_explorer_system_prompt,
    goal_oriented_knowledge_explorer_task_prompt,
)
from modules.content_generator.schemas import KnowledgePoints
from modules.content_generator.utils import (
    build_session_adaptation_contract,
    format_session_adaptation_contract,
)

logger = logging.getLogger(__name__)


def _coerce_knowledge_points_output(raw_output: Any) -> dict[str, list[dict[str, Any]]]:
    if isinstance(raw_output, list):
        knowledge_points = raw_output
    elif isinstance(raw_output, dict):
        knowledge_points = raw_output.get("knowledge_points", [])
    else:
        knowledge_points = []

    if not isinstance(knowledge_points, list):
        knowledge_points = []

    normalized_items: list[dict[str, Any]] = []
    for item in knowledge_points:
        if not isinstance(item, dict):
            continue
        normalized_items.append(item)
    return {"knowledge_points": normalized_items}


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, Mapping):
                return parsed
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, Mapping):
                return parsed
        except Exception:
            pass
    return {}


def _normalize_name_for_dedupe(name: Any) -> str:
    lowered = str(name or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _is_generic_scaffolding_name(name: str) -> bool:
    generic_names = {
        "introduction",
        "overview",
        "conclusion",
        "summary",
        "recap",
    }
    normalized = _normalize_name_for_dedupe(name)
    return normalized in generic_names


def _perception_mode(session_adaptation_contract: Any) -> str:
    contract = _to_mapping(session_adaptation_contract)
    perception = contract.get("perception", {})
    if isinstance(perception, Mapping):
        return str(perception.get("mode", "")).strip().lower()
    return ""


def _sort_when_ambiguous(items: list[dict[str, Any]], session_adaptation_contract: Any) -> list[dict[str, Any]]:
    if len(items) < 2:
        return items
    roles = [str(item.get("role", "")).strip().lower() for item in items if isinstance(item, dict)]
    role_counts: dict[str, int] = {}
    for role in roles:
        role_counts[role] = role_counts.get(role, 0) + 1
    has_ties = any(count > 1 for count in role_counts.values())
    if not has_ties:
        return items

    mode = _perception_mode(session_adaptation_contract)
    if mode == "application_first":
        priority = {"practical": 0, "foundational": 1, "strategic": 2}
    else:
        priority = {"foundational": 0, "practical": 1, "strategic": 2}

    indexed = list(enumerate(items))
    indexed.sort(
        key=lambda pair: (
            priority.get(str(pair[1].get("role", "")).strip().lower(), 99),
            pair[0],
        )
    )
    return [item for _, item in indexed]


def _drop_near_duplicate_points(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _normalize_name_for_dedupe(item.get("name", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_generic_scaffolding_points(
    items: list[dict[str, Any]],
    learning_session: Any,
) -> list[dict[str, Any]]:
    session = _to_mapping(learning_session)
    session_text = " ".join(
        str(session.get(field, "") or "")
        for field in ("title", "abstract", "desired_outcome_when_completed")
    ).lower()
    filtered: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if _is_generic_scaffolding_name(name) and _normalize_name_for_dedupe(name) not in session_text:
            continue
        filtered.append(item)
    if filtered:
        return filtered
    return items


def _post_process_knowledge_points(
    output: dict[str, list[dict[str, Any]]],
    payload: "KnowledgeExplorePayload",
) -> dict[str, list[dict[str, Any]]]:
    items = list(output.get("knowledge_points", []))
    items = [item for item in items if isinstance(item, dict)]
    items = _drop_near_duplicate_points(items)
    items = _filter_generic_scaffolding_points(items, payload.learning_session)
    items = _sort_when_ambiguous(items, payload.session_adaptation_contract)
    return {"knowledge_points": items}


class KnowledgeExplorePayload(BaseModel):
    learner_profile: Any
    learning_path: Any
    learning_session: Any
    session_adaptation_contract: Any = ""
    schema_repair_feedback: str = ""

    @field_validator("learner_profile", "learning_path", "learning_session", "session_adaptation_contract")
    @classmethod
    def coerce_jsonish(cls, v: Any) -> Any:
        if isinstance(v, BaseModel):
            return v.model_dump()
        if isinstance(v, Mapping):
            return dict(v)
        if isinstance(v, str):
            return v.strip()
        return v

class GoalOrientedKnowledgeExplorer(BaseAgent):
    name: str = "GoalOrientedKnowledgeExplorer"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=goal_oriented_knowledge_explorer_system_prompt, jsonalize_output=True)

    def explore(self, payload: KnowledgeExplorePayload | Mapping[str, Any] | str | dict):
        if not isinstance(payload, KnowledgeExplorePayload):
            payload = KnowledgeExplorePayload.model_validate(payload)

        first_payload = payload.model_dump()
        raw_output = self.invoke(first_payload, task_prompt=goal_oriented_knowledge_explorer_task_prompt)
        coerced_output = _post_process_knowledge_points(_coerce_knowledge_points_output(raw_output), payload)
        try:
            validated_output = KnowledgePoints.model_validate(coerced_output)
            return validated_output.model_dump()
        except ValidationError as exc:
            errors_json = json.dumps(exc.errors(), ensure_ascii=True)
            logger.warning("Knowledge explorer schema mismatch, issuing one repair retry: %s", errors_json)

        retry_payload = payload.model_dump()
        retry_payload["schema_repair_feedback"] = (
            "Your previous output failed schema validation. "
            "Fix every error and return only valid JSON matching the exact schema.\n"
            f"Validation errors: {errors_json}"
        )
        repaired_output = self.invoke(retry_payload, task_prompt=goal_oriented_knowledge_explorer_task_prompt)
        repaired_coerced = _post_process_knowledge_points(_coerce_knowledge_points_output(repaired_output), payload)
        validated_output = KnowledgePoints.model_validate(repaired_coerced)
        return validated_output.model_dump()


def explore_knowledge_points_with_llm(
    llm,
    learner_profile,
    learning_path,
    learning_session,
    *,
    session_adaptation_contract: Mapping[str, Any] | None = None,
):
    """Convenience wrapper to explore knowledge points for a session using the agent.

    Mirrors the selected helper signature and behavior.
    """
    if session_adaptation_contract is None:
        session_adaptation_contract = build_session_adaptation_contract(learning_session, learner_profile)
    input_dict = {
        "learner_profile": learner_profile,
        "learning_path": learning_path,
        "learning_session": learning_session,
        "session_adaptation_contract": format_session_adaptation_contract(session_adaptation_contract),
        "schema_repair_feedback": "",
    }
    explorer = GoalOrientedKnowledgeExplorer(llm)
    return explorer.explore(input_dict)
