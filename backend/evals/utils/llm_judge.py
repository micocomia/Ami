"""
Shared LLM-as-a-Judge helper.

Calls an LLM with a structured scoring prompt and parses the JSON response.
Each dimension returns a dict with {"score": int, "reason": str}.
"""

import json
import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


def _get_judge_llm():
    from evals.config import JUDGE_PROVIDER, JUDGE_MODEL

    if JUDGE_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=JUDGE_MODEL, temperature=0)
    elif JUDGE_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=JUDGE_MODEL, temperature=0)
    else:
        raise ValueError(f"Unsupported judge provider: {JUDGE_PROVIDER}")


def judge(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """
    Call the judge LLM with system + user prompts.
    Returns parsed JSON dict.  Falls back to {"error": <message>} on failure.
    """
    llm = _get_judge_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    try:
        response = llm.invoke(messages)
        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


def average_score(results: list[dict], dimension: str) -> float | None:
    """
    Compute the mean score for a dimension across a list of judge result dicts.
    Returns None if no valid scores found.
    """
    scores = []
    for r in results:
        dim = r.get(dimension, {})
        if isinstance(dim, dict) and "score" in dim:
            scores.append(dim["score"])
    return round(sum(scores) / len(scores), 2) if scores else None
