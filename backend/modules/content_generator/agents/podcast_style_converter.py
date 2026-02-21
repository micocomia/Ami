from __future__ import annotations

from typing import Any

from base import BaseAgent
from modules.content_generator.prompts.podcast_style_converter import (
    FULL_SYSTEM_PROMPT,
    RICH_TEXT_SYSTEM_PROMPT,
    TASK_PROMPT,
)


class PodcastStyleConverter(BaseAgent):
    name: str = "PodcastStyleConverter"

    def __init__(self, model: Any, mode: str = "full"):
        system_prompt = {
            "full": FULL_SYSTEM_PROMPT,
            "rich_text": RICH_TEXT_SYSTEM_PROMPT,
        }[mode]
        super().__init__(model=model, system_prompt=system_prompt, jsonalize_output=True)

    def convert(self, payload) -> str:
        raw = self.invoke(payload, task_prompt=TASK_PROMPT)
        return raw["document"]


def convert_to_podcast_with_llm(llm, document: str, learner_profile, mode: str = "full") -> str:
    """Convert a learning document to podcast style using the LLM.

    Args:
        llm: Language model instance.
        document: The markdown learning document to convert.
        learner_profile: Learner profile dict (or string representation).
        mode: 'full' for Host-Expert dialogue, 'rich_text' for narrative rewrite.

    Returns:
        Converted document as a markdown string.
    """
    return PodcastStyleConverter(llm, mode=mode).convert(
        {"document": document, "learner_profile": learner_profile}
    )
