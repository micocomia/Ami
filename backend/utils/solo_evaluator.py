"""LLM-based evaluation of free-text quiz responses using SOLO Taxonomy."""

from __future__ import annotations

import json
from typing import Any, Tuple

from pydantic import BaseModel


class SOLOEvaluation(BaseModel):
    solo_level: str  # prestructural | unistructural | multistructural | relational | extended_abstract
    score: float  # 0.0–1.0 normalized score
    feedback: str  # Qualitative feedback for the learner


_SOLO_EVALUATION_PROMPT = """You are a pedagogical assessment agent using the SOLO Taxonomy to evaluate student responses.

## SOLO Taxonomy Rubric

Given the question, the rubric, and the student's response, classify the response into one of five SOLO levels:

1. **Prestructural** (score: 0.0): The student misses the point entirely or provides irrelevant information.
2. **Unistructural** (score: 0.25): The response focuses on one relevant aspect but lacks depth or detail.
3. **Multistructural** (score: 0.5): The response identifies several relevant aspects but treats them as independent facts without integration.
4. **Relational** (score: 0.75): The response integrates separate parts into a coherent whole, showing how they relate to one another.
5. **Extended Abstract** (score: 1.0): The response generalizes the integrated whole to new, untaught contexts or makes predictions.

## Input

**Question:** {question}

**Question-Specific Rubric:** {rubric}

**Example Answer (Relational/Extended Abstract):** {example_answer}

**Student Response:** {student_response}

## Output

Return a JSON object with no other text or markdown:
{{
    "solo_level": "one of: prestructural, unistructural, multistructural, relational, extended_abstract",
    "score": <float 0.0 to 1.0>,
    "feedback": "Brief qualitative feedback explaining the classification and how the student could improve."
}}"""


_SHORT_ANSWER_EVALUATION_PROMPT = """Given the question and expected answer, determine if the student's response is correct.
The response does not need to match word-for-word — accept any answer that conveys the same meaning.

Question: {question}
Expected Answer: {expected_answer}
Student Response: {student_response}

Return a JSON object with no other text or markdown:
{{"is_correct": true or false, "feedback": "brief explanation"}}"""


def evaluate_free_text_response(
    llm: Any,
    question: str,
    rubric: str,
    example_answer: str,
    student_response: str,
) -> SOLOEvaluation:
    """Evaluate a single free-text response using SOLO taxonomy via LLM."""
    prompt = _SOLO_EVALUATION_PROMPT.format(
        question=question,
        rubric=rubric,
        example_answer=example_answer,
        student_response=student_response,
    )
    raw = llm.invoke(prompt)
    # Handle both string and message-like responses
    content = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
    content = content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(content)
    return SOLOEvaluation.model_validate(data)


def evaluate_short_answer_response(
    llm: Any,
    question: str,
    expected_answer: str,
    student_response: str,
) -> Tuple[bool, str]:
    """Evaluate a short answer using LLM semantic matching (not exact string match).

    Returns (is_correct: bool, feedback: str).
    """
    prompt = _SHORT_ANSWER_EVALUATION_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        student_response=student_response,
    )
    raw = llm.invoke(prompt)
    content = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    data = json.loads(content)
    return bool(data.get("is_correct", False)), str(data.get("feedback", ""))
