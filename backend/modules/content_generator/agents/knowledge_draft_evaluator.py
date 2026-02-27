from __future__ import annotations

import re
from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator

from base import BaseAgent
from modules.content_generator.prompts.knowledge_draft_evaluator import (
    knowledge_draft_batch_evaluator_output_format,
    knowledge_draft_batch_evaluator_task_prompt,
    knowledge_draft_evaluator_system_prompt,
    knowledge_draft_evaluator_task_prompt,
)
from modules.content_generator.schemas import (
    BatchKnowledgeDraftEvaluation,
    KnowledgeDraftEvaluation,
)


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


class BatchKnowledgeDraftEvaluationPayload(BaseModel):
    learner_profile: Any = Field(default_factory=dict)
    learning_session: Any = Field(default_factory=dict)
    session_adaptation_contract: Any = ""
    drafts: Any = Field(default_factory=list)

    @field_validator(
        "learner_profile",
        "learning_session",
        "session_adaptation_contract",
        "drafts",
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

    placeholder_markers = {
        "tbd", "todo", "coming soon", "to be added", "placeholder", "n/a", "lorem ipsum",
    }
    asset_heading_markers = (
        "short story",
        "poem",
        "video",
        "media support",
        "visual walkthrough",
        "audio",
        "image",
        "diagram",
        "resource",
        "watch",
        "listen",
    )

    def _strip_non_prose(text: str) -> str:
        value = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        value = re.sub(r"^#{2,3}\s+.+$", " ", value, flags=re.MULTILINE)
        value = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", value)
        value = re.sub(r"<audio[^>]*>.*?</audio>", " ", value, flags=re.DOTALL)
        value = re.sub(r"<video[^>]*>.*?</video>", " ", value, flags=re.DOTALL)
        value = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", value)
        value = re.sub(r"^\s*[-*+]\s+.*$", " ", value, flags=re.MULTILINE)
        value = re.sub(r"^\s*\|.*\|\s*$", " ", value, flags=re.MULTILINE)
        value = re.sub(r"[\|\-\*\d.`:_>#]+", " ", value)
        return value

    def _prose_word_count(text: str) -> int:
        cleaned = _strip_non_prose(text)
        words = re.findall(r"[A-Za-z]{3,}", cleaned)
        return len(words)

    def _contains_placeholder_only(text: str) -> bool:
        stripped = _strip_non_prose(text).strip().lower()
        if not stripped:
            return False
        normalized = re.sub(r"\s+", " ", stripped)
        return normalized in placeholder_markers

    def _asset_only_section(text: str) -> bool:
        has_asset_markup = bool(
            re.search(r"!\[[^\]]*\]\([^)]+\)", text)
            or re.search(r"<audio[^>]*>", text)
            or re.search(r"<video[^>]*>", text)
            or re.search(r"^\s*\|.*\|\s*$", text, flags=re.MULTILINE)
            or re.search(r"```", text)
        )
        return has_asset_markup and _prose_word_count(text) < 8

    def _instructional_body_excluding_asset_subsections(text: str) -> str:
        subsection_matches = list(re.finditer(r"^(###|####)\s+(.+)$", text, flags=re.MULTILINE))
        if not subsection_matches:
            return text

        parts: list[str] = []
        first_match = subsection_matches[0]
        prelude = text[: first_match.start()]
        if prelude.strip():
            parts.append(prelude)

        for sub_idx, sub_match in enumerate(subsection_matches):
            title = sub_match.group(2).strip().lower()
            start = sub_match.end()
            end = subsection_matches[sub_idx + 1].start() if sub_idx + 1 < len(subsection_matches) else len(text)
            block = text[start:end]
            if any(marker in title for marker in asset_heading_markers):
                continue
            parts.append(block)
        return "\n".join(parts).strip()

    for idx, match in enumerate(section_matches):
        start = match.end()
        end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(content)
        body = content[start:end].strip()
        if not body:
            title = match.group(1).strip()
            issues.append(f"Section '{title}' has no content.")
            directives.append(f"Add teaching content under the ## heading '{title}' before starting a new section.")
            continue

        if _contains_placeholder_only(body):
            title = match.group(1).strip()
            issues.append(f"Section '{title}' contains placeholder text only.")
            directives.append(
                f"Replace placeholder content in '{title}' with real instructional explanation and examples."
            )
            continue

        if _asset_only_section(body):
            title = match.group(1).strip()
            issues.append(f"Section '{title}' is asset-heavy but lacks explanatory prose.")
            directives.append(
                f"Add concise explanatory teaching prose in '{title}' before or after assets/media."
            )
            continue

        instructional_body = _instructional_body_excluding_asset_subsections(body)
        if _prose_word_count(instructional_body) < 10:
            title = match.group(1).strip()
            issues.append(
                f"Section '{title}' lacks instructional explanation outside media/narrative support blocks."
            )
            directives.append(
                f"In '{title}', add clear teaching prose (concept/rule/usage) before or between supporting media/narrative blocks."
            )
            continue

        prose_words = _prose_word_count(body)
        if prose_words < 12:
            # Allow compact code/table-heavy instructional sections if they still include explanatory context.
            has_code_or_table = bool(re.search(r"```|^\s*\|.*\|\s*$", body, flags=re.MULTILINE))
            has_subsections = bool(re.search(r"^###\s+.+$", body, flags=re.MULTILINE))
            if has_code_or_table and prose_words >= 8:
                continue
            if has_subsections:
                subtree_has_prose = False
                sub_matches = list(re.finditer(r"^###\s+(.+)$", body, flags=re.MULTILINE))
                for sub_idx, sub_match in enumerate(sub_matches):
                    sub_start = sub_match.end()
                    sub_end = sub_matches[sub_idx + 1].start() if sub_idx + 1 < len(sub_matches) else len(body)
                    sub_body = body[sub_start:sub_end]
                    if _prose_word_count(sub_body) >= 8:
                        subtree_has_prose = True
                        break
                if subtree_has_prose:
                    continue
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

    def evaluate_batch(self, payload: BatchKnowledgeDraftEvaluationPayload | Mapping[str, Any] | str) -> dict:
        if not isinstance(payload, BatchKnowledgeDraftEvaluationPayload):
            payload = BatchKnowledgeDraftEvaluationPayload.model_validate(payload)
        data = payload.model_dump()
        raw_output = self.invoke(
            {
                **data,
                "batch_output_format": knowledge_draft_batch_evaluator_output_format,
            },
            task_prompt=knowledge_draft_batch_evaluator_task_prompt,
        )
        validated_output = BatchKnowledgeDraftEvaluation.model_validate(raw_output)
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


def evaluate_knowledge_draft_batch_with_llm(
    llm: Any,
    learner_profile: Mapping[str, Any],
    learning_session: Mapping[str, Any],
    drafts: list[dict[str, Any]],
    session_adaptation_contract: Any,
) -> dict:
    evaluator = KnowledgeDraftEvaluator(llm)
    payload = {
        "learner_profile": learner_profile,
        "learning_session": learning_session,
        "drafts": drafts,
        "session_adaptation_contract": session_adaptation_contract,
    }
    return evaluator.evaluate_batch(payload)
