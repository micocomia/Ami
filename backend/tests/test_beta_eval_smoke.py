import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.Beta.eval_api_perf import VERSION_KEY, run_eval_api_perf
from evals.Beta.eval_content import run_eval_content
from evals.Beta.eval_plan import run_eval_plan
from evals.Beta.eval_rag import run_eval_rag
from evals.Beta.eval_skill_gap import run_eval_skill_gap


def test_beta_eval_modules_smoke(monkeypatch):
    real_client = httpx.Client
    scenario = {
        "id": "S1",
        "learning_goal": "Learn Python basics",
        "learner_information": "I am new to programming.",
        "learner_information_enhanced": "Learning Persona: Balanced Learner. I am new to programming.",
    }
    rag_case = {
        "goal_id": "G2",
        "learning_goal": "Learn Python basics",
        "knowledge_point": "Variables",
        "ground_truth": "Variables store values.",
        "ground_truth_facts": ["Variables store values."],
        "case_type": "metadata",
        "case_id": "R1",
        "expected_course_code": "6.0001",
        "expected_keywords": ["variables"],
        "query": "What is a variable in Python?",
        "expected_lecture_numbers": [1],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/refine-learning-goal"):
            return httpx.Response(200, json={"refined_goal": "Learn Python basics"})
        if path.endswith("/identify-skill-gap-with-info"):
            return httpx.Response(
                200,
                json={
                    "refined_goal": "Learn Python basics",
                    "skill_requirements": [{"name": "Variables"}],
                    "skill_gaps": [{"name": "Variables", "current_level": "unlearned", "required_level": "beginner"}],
                },
            )
        if path.endswith("/create-learner-profile-with-info"):
            return httpx.Response(
                200,
                json={
                    "learner_profile": {
                        "learning_preferences": {"fslsm_dimensions": {"fslsm_input": 0.0}},
                        "cognitive_status": {"in_progress_skills": [{"current_level": "beginner"}]},
                    }
                },
            )
        if path.endswith("/schedule-learning-path"):
            return httpx.Response(
                200,
                json={
                    "learning_path": [
                        {
                            "title": "Session 1",
                            "associated_skills": ["Variables"],
                            "desired_outcome_when_completed": [{"name": "Variables", "level": "beginner"}],
                            "has_checkpoint_challenges": True,
                            "thinking_time_buffer_minutes": 5,
                            "navigation_mode": "linear",
                        }
                    ]
                },
            )
        if path.endswith("/generate-learning-content"):
            return httpx.Response(
                200,
                json={"document": "## Variables\nVariables store values.", "quizzes": {"single_choice_questions": []}},
            )
        if path.endswith("/chat-with-tutor"):
            return httpx.Response(
                200,
                json={
                    "response": "Start by learning what variables are.",
                    "profile_updated": False,
                    "retrieval_trace": {
                        "contexts": [
                            {
                                "page_content": "Variables store values.",
                                "source_type": "verified_content",
                                "course_code": "6.0001",
                                "file_name": "lec_1.pdf",
                                "lecture_number": 1,
                            }
                        ],
                        "tool_calls": [{"tool_name": "retrieve_vector_context", "query": "What is a variable in Python?"}],
                    },
                },
            )
        raise AssertionError(f"Unhandled path: {path}")

    def fake_client(*args, **kwargs):
        return real_client(transport=httpx.MockTransport(handler))

    canned_scores = {
        "completeness": {"score": 4, "reason": "good"},
        "gap_calibration": {"score": 4, "reason": "good"},
        "goal_refinement_quality": {"score": 4, "reason": "good"},
        "confidence_validity": {"score": 4, "reason": "good"},
        "expert_calibration": {"score": 4, "reason": "good"},
        "solo_level_accuracy": {"score": 4, "reason": "good"},
        "pedagogical_sequencing": {"score": 4, "reason": "good"},
        "skill_coverage": {"score": 4, "reason": "good"},
        "scope_appropriateness": {"score": 4, "reason": "good"},
        "session_abstraction_quality": {"score": 4, "reason": "good"},
        "fslsm_structural_alignment": {"score": 4, "reason": "good"},
        "solo_outcome_progression": {"score": 4, "reason": "good"},
        "cognitive_level_match": {"score": 4, "reason": "good"},
        "factual_accuracy": {"score": 4, "reason": "good"},
        "quiz_alignment": {"score": 4, "reason": "good"},
        "engagement_quality": {"score": 4, "reason": "good"},
        "fslsm_content_adaptation": {"score": 4, "reason": "good"},
        "solo_cognitive_alignment": {"score": 4, "reason": "good"},
    }

    monkeypatch.setattr("evals.Beta.eval_api_perf.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_skill_gap.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_plan.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_content.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_rag.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_api_perf.httpx.Client", fake_client)
    monkeypatch.setattr("evals.Beta.eval_skill_gap.httpx.Client", fake_client)
    monkeypatch.setattr("evals.Beta.eval_plan.httpx.Client", fake_client)
    monkeypatch.setattr("evals.Beta.eval_content.httpx.Client", fake_client)
    monkeypatch.setattr("evals.Beta.eval_rag.httpx.Client", fake_client)
    monkeypatch.setattr("evals.Beta.eval_skill_gap.judge", lambda *args, **kwargs: canned_scores)
    monkeypatch.setattr("evals.Beta.eval_plan.judge", lambda *args, **kwargs: canned_scores)
    monkeypatch.setattr("evals.Beta.eval_content.judge", lambda *args, **kwargs: canned_scores)

    perf_results = run_eval_api_perf([scenario], base_url="http://test/v1")
    skill_gap_results = run_eval_skill_gap([scenario], prefetched_runs=perf_results, base_url="http://test/v1")
    plan_results = run_eval_plan([scenario], prefetched_runs=perf_results, base_url="http://test/v1")
    content_results = run_eval_content([scenario], prefetched_runs=perf_results, base_url="http://test/v1")
    rag_results = run_eval_rag([rag_case], base_url="http://test/v1")

    assert perf_results[VERSION_KEY]["summary"]["chat_with_tutor"]["p50_ms"] >= 0
    assert skill_gap_results[VERSION_KEY][0]["scores"]["completeness"]["score"] == 4
    assert plan_results[VERSION_KEY][0]["scores"]["pedagogical_sequencing"]["score"] == 4
    assert content_results[VERSION_KEY][0]["scores"]["cognitive_level_match"]["score"] == 4
    assert rag_results[VERSION_KEY][0]["contexts"] == ["Variables store values."]
