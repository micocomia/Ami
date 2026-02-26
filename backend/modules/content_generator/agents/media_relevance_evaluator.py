from __future__ import annotations

from typing import Any, List

from base import BaseAgent
from base.llm_factory import LLMFactory
from modules.content_generator.prompts.media_relevance_evaluator import (
    media_relevance_evaluator_system_prompt,
    media_relevance_evaluator_task_prompt,
)
from modules.content_generator.schemas import MediaRelevanceResult


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
) -> List[dict]:
    """Use MediaRelevanceEvaluator to filter candidate resources for session relevance.
    Falls back to returning all resources if evaluation fails."""
    if not resources:
        return resources

    def _resource_line(i, r):
        label = f"[{r['type'].upper()}] \"{r['title']}\""
        desc = r.get("snippet") or r.get("description") or ""
        return f"{i + 1}. {label}" + (f" — {desc[:200]}" if desc else "")

    resource_lines = "\n".join(_resource_line(i, r) for i, r in enumerate(resources))
    payload = {
        "session_title": session_title,
        "key_topics": ", ".join(knowledge_point_names) if knowledge_point_names else session_title,
        "resources": resource_lines,
    }
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
        if len(judgments) == len(resources):
            return [r for r, keep in zip(resources, judgments) if keep]
    except Exception:
        try:
            # Compatibility fallback: use the caller-provided model if mini is unavailable.
            if llm is not None:
                evaluator = MediaRelevanceEvaluator(llm)
                result = evaluator.evaluate(payload)
                judgments = result.get("relevance", [])
                if len(judgments) == len(resources):
                    return [r for r, keep in zip(resources, judgments) if keep]
        except Exception:
            pass

    return resources  # graceful fallback: return all candidates
