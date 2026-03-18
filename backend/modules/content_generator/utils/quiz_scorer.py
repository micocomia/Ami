"""Quiz scoring and mastery threshold utilities.

Pure deterministic functions — no LLM calls required.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union


# Ordered from lowest to highest proficiency
_PROFICIENCY_ORDER = ["beginner", "intermediate", "advanced", "expert"]


def compute_quiz_score(
    quiz_data: Dict[str, Any],
    user_answers: Dict[str, Any],
    llm_evaluations: Optional[Dict[str, Any]] = None,
) -> Tuple[Union[int, float], int, float]:
    """Score user answers against quiz data.

    Returns:
        (correct_count, total_count, score_percentage)

    Scoring rules:
    - single_choice: exact match on correct_option index value
    - multiple_choice: exact set match on correct_options indices
    - true_false: exact match on correct_answer boolean
    - short_answer: LLM semantic match if llm_evaluations provided, else case-insensitive exact match
    - open_ended: fractional score (0.0–1.0) from llm_evaluations if provided, else skipped

    Args:
        quiz_data: The quiz definition dict.
        user_answers: The learner's submitted answers.
        llm_evaluations: Optional pre-computed LLM results with keys:
            - "short_answer_evaluations": list of {"is_correct": bool, "feedback": str}
            - "open_ended_evaluations": list of {"solo_level": str, "score": float, "feedback": str}
    """
    def resolve_option_value(options: List[Any], key: Any) -> str:
        if isinstance(key, int) and 0 <= key < len(options):
            return str(options[key])
        if isinstance(key, str):
            stripped = key.strip()
            if stripped.isdigit():
                idx = int(stripped)
                if 0 <= idx < len(options):
                    return str(options[idx])
            if key in options:
                return str(key)
        return str(key) if key is not None else ""

    def normalize_answer_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v is not None and str(v).strip() != ""]
        return [str(value)]

    def resolve_multiple_correct_options(question: Dict[str, Any]) -> List[str]:
        options = question.get("options", [])
        values = []
        for key in question.get("correct_options", []):
            resolved = resolve_option_value(options, key)
            if resolved and resolved not in values:
                values.append(resolved)
        return values

    total = 0
    correct = 0.0

    short_answer_evals = (llm_evaluations or {}).get("short_answer_evaluations", [])
    open_ended_evals = (llm_evaluations or {}).get("open_ended_evaluations", [])

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
                correct_option = resolve_option_value(q.get("options", []), q.get("correct_option"))
                if str(answers[i]) == correct_option:
                    correct += 1

            elif q_type == "multiple_choice_questions":
                correct_set = set(resolve_multiple_correct_options(q))
                if set(normalize_answer_list(answers[i])) == correct_set:
                    correct += 1

            elif q_type == "true_false_questions":
                expected = "True" if q["correct_answer"] else "False"
                if str(answers[i]) == expected:
                    correct += 1

            elif q_type == "short_answer_questions":
                if i < len(short_answer_evals):
                    # Use LLM semantic evaluation
                    if short_answer_evals[i].get("is_correct", False):
                        correct += 1
                else:
                    # Fallback: exact case-insensitive match
                    if (
                        str(answers[i]).strip().lower()
                        == q["expected_answer"].strip().lower()
                    ):
                        correct += 1

    # Open-ended questions: each contributes a fractional score
    open_ended_questions = quiz_data.get("open_ended_questions", [])
    open_ended_answers = user_answers.get("open_ended_questions", [])
    for i, q in enumerate(open_ended_questions):
        total += 1
        if i >= len(open_ended_answers) or open_ended_answers[i] is None:
            continue
        if i < len(open_ended_evals):
            correct += float(open_ended_evals[i].get("score", 0.0))
        # If no evaluation provided for this question, score is 0 (already no addition)

    pct = (correct / total * 100) if total > 0 else 0.0
    return correct, total, pct


def build_quiz_feedback(
    quiz_data: Dict[str, Any],
    user_answers: Dict[str, Any],
    llm_evaluations: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build per-question feedback for all quiz types.

    Returns a dict keyed by question type with an aligned item per question.
    """
    def is_blank_answer(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, list):
            return len(value) == 0
        return False

    def resolve_option_value(options: List[Any], key: Any) -> str:
        if isinstance(key, int) and 0 <= key < len(options):
            return str(options[key])
        if isinstance(key, str):
            stripped = key.strip()
            if stripped.isdigit():
                idx = int(stripped)
                if 0 <= idx < len(options):
                    return str(options[idx])
            if key in options:
                return str(key)
        return str(key) if key is not None else ""

    def normalize_answer_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v is not None and str(v).strip() != ""]
        return [str(value)]

    def resolve_multiple_correct_options(question: Dict[str, Any]) -> List[str]:
        options = question.get("options", [])
        values = []
        for key in question.get("correct_options", []):
            resolved = resolve_option_value(options, key)
            if resolved and resolved not in values:
                values.append(resolved)
        return values

    result: Dict[str, List[Dict[str, Any]]] = {
        "single_choice_questions": [],
        "multiple_choice_questions": [],
        "true_false_questions": [],
        "short_answer_questions": [],
        "open_ended_questions": [],
    }

    short_answer_evals = (llm_evaluations or {}).get("short_answer_evaluations", [])
    open_ended_evals = (llm_evaluations or {}).get("open_ended_evaluations", [])

    single_questions = quiz_data.get("single_choice_questions", [])
    single_answers = user_answers.get("single_choice_questions", [])
    for i, q in enumerate(single_questions):
        user_raw = single_answers[i] if i < len(single_answers) else None
        user_value = None if is_blank_answer(user_raw) else str(user_raw)
        correct_value = resolve_option_value(q.get("options", []), q.get("correct_option"))
        is_correct = user_value is not None and user_value == correct_value
        reason = ""
        if user_value is None:
            reason = "No answer provided."
        elif not is_correct:
            reason = f"You selected '{user_value}', but the correct answer is '{correct_value}'."
        result["single_choice_questions"].append(
            {
                "is_correct": is_correct,
                "user_answer": user_value,
                "correct_answer": correct_value,
                "reason": reason,
            }
        )

    multiple_questions = quiz_data.get("multiple_choice_questions", [])
    multiple_answers = user_answers.get("multiple_choice_questions", [])
    for i, q in enumerate(multiple_questions):
        user_raw = multiple_answers[i] if i < len(multiple_answers) else None
        user_values = [] if is_blank_answer(user_raw) else normalize_answer_list(user_raw)
        correct_values = resolve_multiple_correct_options(q)
        user_set = set(user_values)
        correct_set = set(correct_values)
        is_correct = (not is_blank_answer(user_raw)) and user_set == correct_set
        reason = ""
        if is_blank_answer(user_raw):
            reason = "No answer provided."
        elif not is_correct:
            missing = [opt for opt in correct_values if opt not in user_set]
            extra = [opt for opt in user_values if opt not in correct_set]
            fragments = []
            if missing:
                fragments.append(f"missing: {', '.join(missing)}")
            if extra:
                fragments.append(f"incorrect selections: {', '.join(extra)}")
            reason = "Your selection did not match the expected set"
            if fragments:
                reason = f"{reason} ({'; '.join(fragments)})."
            else:
                reason = f"{reason}."
        result["multiple_choice_questions"].append(
            {
                "is_correct": is_correct,
                "user_answer": user_values,
                "correct_answer": correct_values,
                "reason": reason,
            }
        )

    true_false_questions = quiz_data.get("true_false_questions", [])
    true_false_answers = user_answers.get("true_false_questions", [])
    for i, q in enumerate(true_false_questions):
        user_raw = true_false_answers[i] if i < len(true_false_answers) else None
        user_value = None if is_blank_answer(user_raw) else str(user_raw)
        correct_value = "True" if q.get("correct_answer") else "False"
        is_correct = user_value is not None and user_value == correct_value
        reason = ""
        if user_value is None:
            reason = "No answer provided."
        elif not is_correct:
            reason = f"You selected '{user_value}', but the correct answer is '{correct_value}'."
        result["true_false_questions"].append(
            {
                "is_correct": is_correct,
                "user_answer": user_value,
                "correct_answer": correct_value,
                "reason": reason,
            }
        )

    short_questions = quiz_data.get("short_answer_questions", [])
    short_answers = user_answers.get("short_answer_questions", [])
    for i, q in enumerate(short_questions):
        user_raw = short_answers[i] if i < len(short_answers) else None
        user_value = None if is_blank_answer(user_raw) else str(user_raw)
        correct_value = str(q.get("expected_answer", ""))
        eval_feedback = short_answer_evals[i] if i < len(short_answer_evals) else {}
        eval_text = str(eval_feedback.get("feedback", "") or "")
        if user_value is None:
            is_correct = False
            reason = "No answer provided."
        elif i < len(short_answer_evals):
            is_correct = bool(eval_feedback.get("is_correct", False))
            reason = "" if is_correct else (eval_text or f"The expected answer is '{correct_value}'.")
        else:
            is_correct = user_value.strip().lower() == correct_value.strip().lower()
            reason = "" if is_correct else f"The expected answer is '{correct_value}'."
        result["short_answer_questions"].append(
            {
                "is_correct": is_correct,
                "user_answer": user_value,
                "correct_answer": correct_value,
                "reason": reason,
                "feedback": eval_text,
            }
        )

    open_questions = quiz_data.get("open_ended_questions", [])
    open_answers = user_answers.get("open_ended_questions", [])
    for i, q in enumerate(open_questions):
        user_raw = open_answers[i] if i < len(open_answers) else None
        user_value = None if is_blank_answer(user_raw) else str(user_raw)
        eval_feedback = open_ended_evals[i] if i < len(open_ended_evals) else {}
        if user_value is None:
            solo_level = "prestructural"
            score = 0.0
            feedback = "No answer provided."
        else:
            solo_level = str(eval_feedback.get("solo_level", "prestructural"))
            score = float(eval_feedback.get("score", 0.0))
            feedback = str(eval_feedback.get("feedback", "") or "Evaluation unavailable.")
        result["open_ended_questions"].append(
            {
                "user_answer": user_value,
                "reference_answer": str(q.get("example_answer", "")),
                "solo_level": solo_level,
                "score": score,
                "feedback": feedback,
            }
        )

    return result


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


def is_strong_success(
    score_pct: float,
    threshold: float,
    margin: float = 10.0,
    max_score: float = 100.0,
) -> bool:
    """Return True if score reflects a strong mastery success.

    Strong success means the learner is mastered and at least ``margin`` above
    threshold, capped by ``max_score`` so high thresholds still allow a perfect
    score to count.
    """
    target = min(float(max_score), float(threshold) + float(margin))
    return float(score_pct) >= float(threshold) and float(score_pct) >= target


def get_quiz_mix_for_session(
    session: Dict[str, Any],
    quiz_mix_config: Dict[str, Any],
) -> Dict[str, int]:
    """Determine question type counts from the session's highest proficiency level.

    Reuses the same logic as get_mastery_threshold_for_session to find the
    highest proficiency, then returns the corresponding mix dict from quiz_mix_config.
    Falls back to "beginner" mix if no outcomes are present.
    """
    outcomes = session.get("desired_outcome_when_completed", [])

    highest_idx = 0
    for o in outcomes:
        level = o.get("level", "")
        level_str = level.value if hasattr(level, "value") else str(level)
        if level_str in _PROFICIENCY_ORDER:
            idx = _PROFICIENCY_ORDER.index(level_str)
            if idx > highest_idx:
                highest_idx = idx

    level_name = _PROFICIENCY_ORDER[highest_idx]
    # Default to beginner mix if not found
    return dict(quiz_mix_config.get(level_name, quiz_mix_config.get("beginner", {})))
