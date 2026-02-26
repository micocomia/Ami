from __future__ import annotations

from typing import Any, List

from base import BaseAgent


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


def generate_narrative_resources_with_llm(
    llm,
    knowledge_points,
    knowledge_drafts,
    session_title: str,
    max_narratives: int,
    include_tts: bool = False,
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
                    n["audio_url"] = generate_tts_audio(n.get("content", ""))
                except Exception:
                    pass
        except Exception:
            pass
    return narratives

