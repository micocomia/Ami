"""Shared LLM-as-a-Judge helper for Beta evals."""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


def _get_judge_llm():
    from evals.Beta.config import JUDGE_MODEL, JUDGE_PROVIDER

    if JUDGE_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=JUDGE_MODEL, temperature=0)
    if JUDGE_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=JUDGE_MODEL, temperature=0)
    raise ValueError(f"Unsupported judge provider: {JUDGE_PROVIDER}")


def judge(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    llm = _get_judge_llm()
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        return {"error": str(exc)}


def average_score(results: list[dict], dimension: str) -> float | None:
    scores = []
    for result in results:
        dim = result.get(dimension, {})
        if isinstance(dim, dict) and "score" in dim:
            scores.append(dim["score"])
    return round(sum(scores) / len(scores), 2) if scores else None
