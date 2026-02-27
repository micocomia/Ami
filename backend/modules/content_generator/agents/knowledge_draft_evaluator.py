from __future__ import annotations

import re
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.content_generator.prompts.knowledge_draft_evaluator import (
    knowledge_draft_evaluator_system_prompt,
    knowledge_draft_evaluator_task_prompt,
)
from modules.content_generator.schemas import KnowledgeDraftEvaluation


class KnowledgeDraftEvaluationPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_session: Any = Field(default_factory=dict)
    knowledge_point: Any = Field(default_factory=dict)
    session_adaptation_contract: Any = ""
    knowledge_draft: Any = Field(default_factory=dict)

    @field_validator(
        "learner_profile",
        "learning_session",
        "knowledge_point",
        "session_adaptation_contract",
        "knowledge_draft",
    )
    @classmethod
    def coerce_jsonish(cls, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            return value.strip()
        return value


def deterministic_knowledge_draft_audit(knowledge_draft: Any) -> dict[str, Any]:
    """Reject obviously malformed drafts before invoking the evaluator model."""
    draft = dict(knowledge_draft) if isinstance(knowledge_draft, Mapping) else {}
    content = str(draft.get("content", "") or "").strip()

    issues: list[str] = []
    directives: list[str] = []

    if not content:
        issues.append("Draft content is empty.")
        directives.append("Write a complete draft with instructional prose before returning.")

    section_matches = list(re.finditer(r"^##\s+(.+)$", content, re.MULTILINE))
    if not section_matches:
        issues.append("Draft is missing a top-level ## section heading.")
        directives.append("Start the draft with a ## heading and include explanatory content underneath it.")

    for idx, match in enumerate(section_matches):
        start = match.end()
        end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(content)
        body = content[start:end].strip()
        if not body:
            title = match.group(1).strip()
            issues.append(f"Section '{title}' has no content.")
            directives.append(f"Add teaching content under the ## heading '{title}' before starting a new section.")
            continue

        prose_text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
        prose_text = re.sub(r"^#{2,3}\s+.+$", " ", prose_text, flags=re.MULTILINE)
        prose_text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", prose_text)
        prose_text = re.sub(r"<audio[^>]*>.*?</audio>", " ", prose_text, flags=re.DOTALL)
        prose_text = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", prose_text)
        prose_text = re.sub(r"[\|\-\*\d.`:_>#]+", " ", prose_text)
        prose_words = re.findall(r"[A-Za-z]{3,}", prose_text)
        if len(prose_words) < 12:
            title = match.group(1).strip()
            issues.append(f"Section '{title}' lacks substantive explanatory prose.")
            directives.append(
                f"Expand the ## section '{title}' with real instructional explanation; do not rely on headings or media alone."
            )

    if issues:
        return {
            "feedback": {
                "coherence": "Draft structure is not yet usable.",
                "content_completeness": "One or more sections are empty or too skeletal.",
                "personalization": "Structural problems prevent a reliable personalization assessment.",
                "solo_alignment": "Structural problems prevent a reliable SOLO assessment.",
            },
            "is_acceptable": False,
            "issues": issues,
            "improvement_directives": "\n".join(dict.fromkeys(directives)),
        }

    return {
        "feedback": {
            "coherence": "Deterministic structure checks passed.",
            "content_completeness": "Each ## section contains instructional content.",
            "personalization": "Requires evaluator confirmation.",
            "solo_alignment": "Requires evaluator confirmation.",
        },
        "is_acceptable": True,
        "issues": [],
        "improvement_directives": "",
    }


class KnowledgeDraftEvaluator(BaseAgent):
    name: str = "KnowledgeDraftEvaluator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=knowledge_draft_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, payload: KnowledgeDraftEvaluationPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, KnowledgeDraftEvaluationPayload):
            payload = KnowledgeDraftEvaluationPayload.model_validate(payload)
        raw_output = self.invoke(payload.model_dump(), task_prompt=knowledge_draft_evaluator_task_prompt)
        validated_output = KnowledgeDraftEvaluation.model_validate(raw_output)
        return validated_output.model_dump()


def evaluate_knowledge_draft_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_session: Mapping[str, Any],
    knowledge_point: Mapping[str, Any],
    knowledge_draft: Mapping[str, Any],
    session_adaptation_contract: Any,
) -> dict:
    evaluator = KnowledgeDraftEvaluator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_session": learning_session,
        "knowledge_point": knowledge_point,
        "knowledge_draft": knowledge_draft,
        "session_adaptation_contract": session_adaptation_contract,
    }
    return evaluator.evaluate(payload)
