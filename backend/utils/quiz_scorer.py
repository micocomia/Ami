"""Quiz scoring and mastery threshold utilities.

Pure deterministic functions — no LLM calls required.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


# Ordered from lowest to highest proficiency
_PROFICIENCY_ORDER = ["beginner", "intermediate", "advanced", "expert"]


def compute_quiz_score(
    quiz_data: Dict[str, Any],
    user_answers: Dict[str, Any],
) -> Tuple[int, int, float]:
    """Score user answers against quiz data.

    Returns:
        (correct_count, total_count, score_percentage)

    Scoring rules:
    - single_choice: exact match on correct_option index value
    - multiple_choice: exact set match on correct_options indices
    - true_false: exact match on correct_answer boolean
    - short_answer: case-insensitive stripped match on expected_answer
    """
    total = 0
    correct = 0

    for q_type in [
        "single_choice_questions",
        "multiple_choice_questions",
        "true_false_questions",
        "short_answer_questions",
    ]:
        questions = quiz_data.get(q_type, [])
        answers = user_answers.get(q_type, [])
        for i, q in enumerate(questions):
            total += 1
            if i >= len(answers) or answers[i] is None:
                continue

            if q_type == "single_choice_questions":
                correct_option = q["options"][q["correct_option"]]
                if answers[i] == correct_option:
                    correct += 1

            elif q_type == "multiple_choice_questions":
                correct_set = {q["options"][idx] for idx in q["correct_options"]}
                if set(answers[i]) == correct_set:
                    correct += 1

            elif q_type == "true_false_questions":
                expected = "True" if q["correct_answer"] else "False"
                if str(answers[i]) == expected:
                    correct += 1

            elif q_type == "short_answer_questions":
                if (
                    str(answers[i]).strip().lower()
                    == q["expected_answer"].strip().lower()
                ):
                    correct += 1

    pct = (correct / total * 100) if total > 0 else 0.0
    return correct, total, pct


def get_mastery_threshold_for_session(
    session: Dict[str, Any],
    threshold_map: Dict[str, float],
    default: float = 70.0,
) -> float:
    """Determine mastery threshold from the session's highest required proficiency.

    Looks at ``desired_outcome_when_completed`` and picks the highest
    proficiency level, then maps it to a threshold via *threshold_map*.
    """
    outcomes = session.get("desired_outcome_when_completed", [])
    if not outcomes:
        return default

    highest_idx = 0
    for o in outcomes:
        level = o.get("level", "")
        # Handle both string and enum values
        level_str = level.value if hasattr(level, "value") else str(level)
        if level_str in _PROFICIENCY_ORDER:
            idx = _PROFICIENCY_ORDER.index(level_str)
            if idx > highest_idx:
                highest_idx = idx

    level_name = _PROFICIENCY_ORDER[highest_idx]
    return threshold_map.get(level_name, default)
