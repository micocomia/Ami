from __future__ import annotations

import re
from typing import Any, List

from base import BaseAgent
from base.llm_factory import LLMFactory
from modules.content_generator.prompts.media_relevance_evaluator import (
    media_relevance_evaluator_system_prompt,
    media_relevance_evaluator_task_prompt,
)
from modules.content_generator.schemas import MediaRelevanceResult


def _tokens(text: str) -> set[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "your", "into",
        "what", "when", "where", "how", "why", "guide", "course", "lesson",
        "video", "tutorial", "walkthrough", "lecture", "explainer", "talk",
        "podcast", "demo", "introduction", "intro", "basics", "learn",
    }
    toks = {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}
    normalized = set()
    for t in toks:
        normalized.add(t)
        if t.endswith("s") and len(t) > 3:
            normalized.add(t[:-1])
    return {t for t in normalized if t not in stop}


def _is_on_topic(resource: dict, target_tokens: set[str]) -> bool:
    if not target_tokens:
        return True
    candidate_text = " ".join(
        str(resource.get(k, "")) for k in ("title", "snippet", "description", "url")
    )
    candidate_tokens = _tokens(candidate_text)
    overlap = target_tokens.intersection(candidate_tokens)
    return len(overlap) >= 1


def _deterministic_topic_filter(resources: List[dict], session_title: str, knowledge_point_names: List[str]) -> List[dict]:
    target_text = f"{session_title} {' '.join(knowledge_point_names or [])}"
    target_tokens = _tokens(target_text)
    return [r for r in resources if isinstance(r, dict) and _is_on_topic(r, target_tokens)]


class MediaRelevanceEvaluator(BaseAgent):
    name: str = "MediaRelevanceEvaluator"

    def __init__(self, model: Any):
        super().__init__(
            model=model,
            system_prompt=media_relevance_evaluator_system_prompt,
            jsonalize_output=True,
        )

    def evaluate(self, payload: dict) -> dict:
        raw_output = self.invoke(payload, task_prompt=media_relevance_evaluator_task_prompt)
        validated = MediaRelevanceResult.model_validate(raw_output)
        return validated.model_dump()


def filter_media_resources_with_llm(
    llm,
    resources: List[dict],
    session_title: str,
    knowledge_point_names: List[str],
    lightweight_llm: Any = None,
) -> List[dict]:
    """Use MediaRelevanceEvaluator to filter candidate resources for session relevance.
    Strict mode: fail-closed with deterministic topicality gate."""
    if not resources:
        return resources
    prefiltered = _deterministic_topic_filter(resources, session_title, knowledge_point_names)
    if not prefiltered:
        return []

    def _resource_line(i, r):
        label = f"[{r['type'].upper()}] \"{r['title']}\""
        desc = r.get("snippet") or r.get("description") or ""
        return f"{i + 1}. {label}" + (f" — {desc[:200]}" if desc else "")

    resource_lines = "\n".join(_resource_line(i, r) for i, r in enumerate(prefiltered))
    payload = {
        "session_title": session_title,
        "key_topics": ", ".join(knowledge_point_names) if knowledge_point_names else session_title,
        "resources": resource_lines,
    }
    if lightweight_llm is not None:
        try:
            evaluator = MediaRelevanceEvaluator(lightweight_llm)
            result = evaluator.evaluate(payload)
            judgments = result.get("relevance", [])
            if len(judgments) == len(prefiltered):
                kept = [r for r, keep in zip(prefiltered, judgments) if keep]
                return _deterministic_topic_filter(kept, session_title, knowledge_point_names)
        except Exception:
            pass
    try:
        # Use a lightweight model for this binary relevance filter to keep latency/cost low.
        lightweight_llm = LLMFactory.create(
            model="gpt-4o-mini",
            model_provider="openai",
            temperature=0,
        )
        evaluator = MediaRelevanceEvaluator(lightweight_llm)
        result = evaluator.evaluate(payload)
        judgments = result.get("relevance", [])
        if len(judgments) == len(prefiltered):
            kept = [r for r, keep in zip(prefiltered, judgments) if keep]
            return _deterministic_topic_filter(kept, session_title, knowledge_point_names)
    except Exception:
        try:
            # Compatibility fallback: use the caller-provided model if mini is unavailable.
            if llm is not None:
                evaluator = MediaRelevanceEvaluator(llm)
                result = evaluator.evaluate(payload)
                judgments = result.get("relevance", [])
                if len(judgments) == len(prefiltered):
                    kept = [r for r, keep in zip(prefiltered, judgments) if keep]
                    return _deterministic_topic_filter(kept, session_title, knowledge_point_names)
        except Exception:
            pass

    # Fail-closed fallback: keep only deterministic topic matches.
    return prefiltered
