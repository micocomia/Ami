from __future__ import annotations

import re
from typing import Any, List

from base import BaseAgent
from base.llm_factory import LLMFactory
from modules.content_generator.prompts.media_relevance_evaluator import (
    media_relevance_evaluator_system_prompt,
    media_relevance_evaluator_task_prompt,
)
from modules.content_generator.schemas import MediaRelevanceBatchResult


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


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _word_count(text: str) -> int:
    return len([w for w in _normalize_space(text).split(" ") if w])


def _clean_display_title(raw_title: str) -> str:
    title = _normalize_space(raw_title)
    if not title:
        return "Learning Resource"
    title = re.sub(r"\s*[\|\-]\s*(youtube|official|full lecture|watch now)\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
    words = title.split()
    if len(words) > 10:
        title = " ".join(words[:10]).rstrip(".,;:") + "..."
    return title[:90].strip() or "Learning Resource"


def _build_fallback_short_description(resource: dict, session_title: str, knowledge_point_names: List[str]) -> str:
    source = _normalize_space(resource.get("snippet") or resource.get("description") or "")
    if source:
        words = source.split()
        clipped = " ".join(words[:24]).strip().rstrip(".,;:")
        if len(clipped.split()) < 8:
            clipped = f"{clipped} for {session_title}".strip()
        return clipped + "."
    topic = ", ".join([x for x in knowledge_point_names if x][:2]).strip()
    if topic:
        return f"Supports {topic} with focused examples tied to this session."
    return f"Supports key ideas from {session_title or 'this learning session'}."


def _grounding_tokens(resource: dict, session_title: str, knowledge_point_names: List[str]) -> set[str]:
    source_text = " ".join(
        [
            str(resource.get("title", "")),
            str(resource.get("snippet", "")),
            str(resource.get("description", "")),
            str(session_title or ""),
            " ".join(knowledge_point_names or []),
        ]
    )
    return _tokens(source_text)


def _is_grounded_phrase(text: str, allowed_tokens: set[str]) -> bool:
    if not text:
        return False
    if not allowed_tokens:
        return True
    phrase_tokens = _tokens(text)
    if not phrase_tokens:
        return True
    extras = [t for t in phrase_tokens if t not in allowed_tokens]
    return len(extras) <= 12


def _has_topic_overlap(text: str, session_title: str, knowledge_point_names: List[str]) -> bool:
    target_tokens = _tokens(f"{session_title} {' '.join(knowledge_point_names or [])}")
    if not target_tokens:
        return True
    phrase_tokens = _tokens(text)
    return len(target_tokens.intersection(phrase_tokens)) >= 1


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
        validated = MediaRelevanceBatchResult.model_validate(raw_output)
        return validated.model_dump()


def filter_media_resources_with_llm(
    llm,
    resources: List[dict],
    session_title: str,
    knowledge_point_names: List[str],
    lightweight_llm: Any = None,
) -> List[dict]:
    """Filter media resources and enrich learner-facing labels.

    Fail-closed behavior:
    - topical deterministic prefilter always applies
    - if LLM evaluation fails, keep deterministic results with heuristic labels.
    """
    if not resources:
        return resources

    prefiltered = _deterministic_topic_filter(resources, session_title, knowledge_point_names)
    if not prefiltered:
        return []

    payload = {
        "session_title": session_title,
        "key_topics": ", ".join(knowledge_point_names) if knowledge_point_names else session_title,
        "resources": [
            {
                "index": i,
                "type": str(r.get("type", "")),
                "title": str(r.get("title", "")),
                "snippet": str(r.get("snippet", "")),
                "description": str(r.get("description", "")),
                "url": str(r.get("url", "")),
            }
            for i, r in enumerate(prefiltered)
        ],
    }

    evaluator_model = lightweight_llm
    if evaluator_model is None:
        try:
            evaluator_model = LLMFactory.create(
                model="gpt-4o-mini",
                model_provider="openai",
                temperature=0,
            )
        except Exception:
            evaluator_model = llm

    if evaluator_model is not None:
        try:
            evaluator = MediaRelevanceEvaluator(evaluator_model)
            result = evaluator.evaluate(payload)
            judgments = result.get("relevance", [])
            if len(judgments) == len(prefiltered):
                enriched: List[dict] = []
                for resource, judgment in zip(prefiltered, judgments):
                    keep = bool(judgment.get("keep", True))
                    if not keep:
                        continue

                    allowed_tokens = _grounding_tokens(resource, session_title, knowledge_point_names)
                    fallback_title = _clean_display_title(resource.get("title", ""))
                    fallback_desc = _build_fallback_short_description(resource, session_title, knowledge_point_names)

                    display_title = _normalize_space(judgment.get("display_title", ""))
                    if len(display_title) > 90:
                        display_title = _clean_display_title(display_title)
                    if (
                        not display_title
                        or not _has_topic_overlap(display_title, session_title, knowledge_point_names)
                        or not _is_grounded_phrase(display_title, allowed_tokens)
                    ):
                        display_title = fallback_title

                    short_description = _normalize_space(judgment.get("short_description", ""))
                    short_desc_words = _word_count(short_description)
                    if (
                        not short_description
                        or short_desc_words < 8
                        or short_desc_words > 24
                        or not _has_topic_overlap(short_description, session_title, knowledge_point_names)
                    ):
                        short_description = fallback_desc
                    elif not _is_grounded_phrase(short_description, allowed_tokens):
                        # Accept concise topical paraphrases from evaluator unless they are too unconstrained.
                        if _word_count(short_description) > 24:
                            short_description = fallback_desc
                    if not short_description:
                        short_description = fallback_desc

                    item = dict(resource)
                    item["display_title"] = display_title
                    item["short_description"] = short_description
                    if judgment.get("confidence") is not None:
                        item["relevance_confidence"] = judgment.get("confidence")
                    enriched.append(item)
                return _deterministic_topic_filter(enriched, session_title, knowledge_point_names)
        except Exception:
            pass

    fallback_enriched: List[dict] = []
    for resource in prefiltered:
        item = dict(resource)
        item["display_title"] = _clean_display_title(resource.get("title", ""))
        item["short_description"] = _build_fallback_short_description(resource, session_title, knowledge_point_names)
        fallback_enriched.append(item)
    return fallback_enriched
