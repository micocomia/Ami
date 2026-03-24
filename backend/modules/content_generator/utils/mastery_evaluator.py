"""Mastery evaluation utility: quiz scoring, LLM evaluation, and FSLSM evidence update."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from modules.learner_profiler.utils import fslsm_adaptation
from modules.content_generator.utils.quiz_scorer import (
    build_quiz_feedback,
    compute_quiz_score,
    get_mastery_threshold_for_session,
    is_strong_success,
)
from utils.solo_evaluator import evaluate_free_text_response, evaluate_short_answer_response


def evaluate_mastery_submission(
    llm: Any,
    quiz_data: Dict[str, Any],
    quiz_answers: Dict[str, Any],
    session: Dict[str, Any],
    adaptation_state: Dict[str, Any],
    profile: Dict[str, Any],
    learning_content_payload: Dict[str, Any],
    mastery_threshold_by_proficiency: Dict[str, Any],
    mastery_threshold_default: float,
    adaptation_daily_cap: float,
) -> Dict[str, Any]:
    """Evaluate quiz answers, compute mastery score, and apply FSLSM evidence updates.

    Does not perform any store writes. Returns a result dict with:
        - score_percentage, correct_count, total_count, is_mastered, threshold
        - fslsm_adjustments: dict of FSLSM dimension adjustments (empty if none)
        - updated_profile: profile with FSLSM adjustments applied (if any)
        - updated_adaptation_state: adaptation state with evidence windows updated
        - short_answer_feedback: list of per-question feedback dicts
        - open_ended_feedback: list of per-question feedback dicts
        - quiz_feedback: deterministic + LLM-enhanced per-question explanation payload
    """
    short_answer_feedback: List[Dict[str, Any]] = []
    open_ended_feedback: List[Dict[str, Any]] = []
    llm_evaluations: Dict[str, Any] = {}

    # Evaluate short-answer questions
    short_answer_qs = quiz_data.get("short_answer_questions", [])
    short_answer_answers = quiz_answers.get("short_answer_questions", [])
    if short_answer_qs and any(a is not None for a in short_answer_answers):
        for i, q in enumerate(short_answer_qs):
            student_ans = short_answer_answers[i] if i < len(short_answer_answers) else None
            if student_ans is None:
                short_answer_feedback.append({"is_correct": False, "feedback": "No answer provided."})
            else:
                try:
                    is_correct, feedback = evaluate_short_answer_response(
                        llm, q["question"], q["expected_answer"], str(student_ans)
                    )
                    short_answer_feedback.append({"is_correct": is_correct, "feedback": feedback})
                except Exception:
                    is_correct = str(student_ans).strip().lower() == q["expected_answer"].strip().lower()
                    short_answer_feedback.append({"is_correct": is_correct, "feedback": ""})
        llm_evaluations["short_answer_evaluations"] = short_answer_feedback

    # Evaluate open-ended questions
    open_ended_qs = quiz_data.get("open_ended_questions", [])
    open_ended_answers = quiz_answers.get("open_ended_questions", [])
    if open_ended_qs and any(a is not None for a in open_ended_answers):
        for i, q in enumerate(open_ended_qs):
            student_ans = open_ended_answers[i] if i < len(open_ended_answers) else None
            if student_ans is None:
                open_ended_feedback.append({
                    "solo_level": "prestructural",
                    "score": 0.0,
                    "feedback": "No answer provided.",
                })
            else:
                try:
                    evaluation = evaluate_free_text_response(
                        llm,
                        q["question"],
                        q["rubric"],
                        q["example_answer"],
                        str(student_ans),
                    )
                    open_ended_feedback.append(evaluation.model_dump())
                except Exception:
                    open_ended_feedback.append({
                        "solo_level": "prestructural",
                        "score": 0.0,
                        "feedback": "Evaluation unavailable.",
                    })
        llm_evaluations["open_ended_evaluations"] = open_ended_feedback

    # Score computation
    correct, total, score_pct = compute_quiz_score(
        quiz_data,
        quiz_answers,
        llm_evaluations if llm_evaluations else None,
    )

    threshold = get_mastery_threshold_for_session(
        session, mastery_threshold_by_proficiency, default=mastery_threshold_default
    )
    is_mastered = score_pct >= threshold

    # FSLSM evidence update
    severe_failure = (not is_mastered) and (score_pct < threshold * 0.8)
    strong_success = is_strong_success(score_pct, threshold, margin=10.0, max_score=100.0)
    signal_keys = fslsm_adaptation.session_signal_keys(session, learning_content_payload)

    updated_adaptation_state = dict(adaptation_state)
    updated_adaptation_state.setdefault("evidence_windows", {})
    for key in signal_keys:
        fslsm_adaptation.append_evidence(
            updated_adaptation_state["evidence_windows"],
            key,
            severe_failure=severe_failure,
            strong_success=strong_success,
        )

    updated_profile, fslsm_adjustments = fslsm_adaptation.update_fslsm_from_evidence(
        profile, updated_adaptation_state, daily_cap=adaptation_daily_cap
    )
    updated_adaptation_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    quiz_feedback = build_quiz_feedback(
        quiz_data=quiz_data,
        user_answers=quiz_answers,
        llm_evaluations=llm_evaluations if llm_evaluations else None,
    )

    return {
        "score_percentage": round(score_pct, 1),
        "correct_count": correct,
        "total_count": total,
        "is_mastered": is_mastered,
        "threshold": threshold,
        "fslsm_adjustments": fslsm_adjustments,
        "updated_profile": updated_profile,
        "updated_adaptation_state": updated_adaptation_state,
        "short_answer_feedback": short_answer_feedback,
        "open_ended_feedback": open_ended_feedback,
        "quiz_feedback": quiz_feedback,
    }
