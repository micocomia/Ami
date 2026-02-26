from __future__ import annotations

from typing import Any, List

from base import BaseAgent
from base.llm_factory import LLMFactory


_SYSTEM_PROMPT = """
You are an educational narrative adapter.
Generate short inline narrative supports for a lesson.

Rules:
- Output JSON only.
- Create concise, pedagogical inserts that reinforce key concepts.
- Each item must be either `short_story` or `poem`.
- Each item must target one section index from the provided section list.
- Keep each item 80-180 words.
""".strip()


_TASK_PROMPT = """
Session title: {session_title}
Max narratives: {max_narratives}

Sections (index | title | topic):
{sections}

Return JSON:
{{
  "narratives": [
    {{
      "type": "short_story" | "poem",
      "title": "string",
      "content": "string",
      "target_section_index": 0
    }}
  ]
}}
""".strip()

_TTS_NORMALIZER_SYSTEM_PROMPT = """
You normalize narrative text for English TTS only.

Rules:
- Output JSON only.
- Preserve meaning and factual content exactly.
- Rewrite non-English terms into clear English phonetic spellings for English TTS.
- Keep text natural for spoken delivery.
- For list items, keep each item on its own line and ensure each item is a complete short sentence.
- Do not add commentary or metadata.
""".strip()

_TTS_NORMALIZER_TASK_PROMPT = """
Normalize this text for English TTS while preserving meaning.

Text:
{content}

Return JSON:
{
  "normalized_text": "string"
}
""".strip()


class NarrativeResourceGenerator(BaseAgent):
    name: str = "NarrativeResourceGenerator"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=_SYSTEM_PROMPT, jsonalize_output=True)

    def generate(self, payload: dict) -> List[dict]:
        raw = self.invoke(payload, task_prompt=_TASK_PROMPT)
        narratives = raw.get("narratives", []) if isinstance(raw, dict) else []
        if not isinstance(narratives, list):
            return []
        cleaned: List[dict] = []
        for n in narratives:
            if not isinstance(n, dict):
                continue
            n_type = n.get("type", "").strip()
            if n_type not in ("short_story", "poem"):
                continue
            cleaned.append(
                {
                    "type": n_type,
                    "title": str(n.get("title", "")).strip() or "Narrative Reflection",
                    "content": str(n.get("content", "")).strip(),
                    "target_section_index": n.get("target_section_index", 0),
                }
            )
        return cleaned


class NarrativeTTSNormalizer(BaseAgent):
    name: str = "NarrativeTTSNormalizer"

    def __init__(self, model: Any):
        super().__init__(model=model, system_prompt=_TTS_NORMALIZER_SYSTEM_PROMPT, jsonalize_output=True)

    def normalize(self, text: str) -> str:
        raw = self.invoke({"content": text or ""}, task_prompt=_TTS_NORMALIZER_TASK_PROMPT)
        normalized = raw.get("normalized_text", "") if isinstance(raw, dict) else ""
        normalized = str(normalized or "").strip()
        return normalized or (text or "")


def _normalize_narrative_content_for_tts(llm, content: str, lightweight_llm: Any = None) -> str:
    if not content:
        return ""
    if lightweight_llm is not None:
        try:
            return NarrativeTTSNormalizer(lightweight_llm).normalize(content)
        except Exception:
            pass
    try:
        mini_llm = LLMFactory.create(
            model="gpt-4o-mini",
            model_provider="openai",
            temperature=0,
        )
        return NarrativeTTSNormalizer(mini_llm).normalize(content)
    except Exception:
        try:
            if llm is not None:
                return NarrativeTTSNormalizer(llm).normalize(content)
        except Exception:
            pass
        return content


def generate_narrative_resources_with_llm(
    llm,
    knowledge_points,
    knowledge_drafts,
    session_title: str,
    max_narratives: int,
    include_tts: bool = False,
    lightweight_llm: Any = None,
) -> List[dict]:
    if llm is None or max_narratives <= 0:
        return []
    if not isinstance(knowledge_points, list):
        knowledge_points = []
    if not isinstance(knowledge_drafts, list):
        knowledge_drafts = []

    sections = []
    for idx, kp in enumerate(knowledge_points):
        if not isinstance(kp, dict):
            continue
        title = ""
        if idx < len(knowledge_drafts) and isinstance(knowledge_drafts[idx], dict):
            title = str(knowledge_drafts[idx].get("title", ""))
        sections.append(
            {
                "index": idx,
                "title": title,
                "topic": str(kp.get("name", "")),
            }
        )

    payload = {
        "session_title": session_title or "",
        "max_narratives": max_narratives,
        "sections": "\n".join(
            f"{s['index']} | {s['title']} | {s['topic']}" for s in sections[:20]
        ),
    }

    try:
        generator = NarrativeResourceGenerator(llm)
        narratives = generator.generate(payload)[:max_narratives]
    except Exception:
        narratives = []

    if include_tts and narratives:
        try:
            from .tts_generator import generate_tts_audio
            for n in narratives:
                try:
                    normalized_content = _normalize_narrative_content_for_tts(
                        llm,
                        n.get("content", ""),
                        lightweight_llm=lightweight_llm,
                    )
                    n["audio_url"] = generate_tts_audio(
                        normalized_content,
                    )
                except Exception:
                    pass
        except Exception:
            pass
    return narratives
