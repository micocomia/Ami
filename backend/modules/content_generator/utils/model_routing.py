from __future__ import annotations

import logging
from typing import Any

from base.llm_factory import LLMFactory

logger = logging.getLogger(__name__)


def get_lightweight_llm(
    primary_llm: Any,
    lightweight_llm: Any = None,
    *,
    model: str = "gpt-4o-mini",
    model_provider: str = "openai",
):
    """Return a lightweight LLM for support tasks, falling back to primary_llm."""
    if lightweight_llm is not None:
        return lightweight_llm

    try:
        return LLMFactory.create(
            model=model,
            model_provider=model_provider,
            temperature=0,
        )
    except Exception as exc:
        logger.warning("Failed to create lightweight model (%s/%s): %s", model_provider, model, exc)
        return primary_llm
