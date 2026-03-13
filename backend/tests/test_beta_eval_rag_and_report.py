import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.Beta.eval_content import _evaluate_content_outputs
from evals.Beta.eval_plan import _evaluate_plan_outputs
from evals.Beta.eval_skill_gap import _evaluate_skill_gap_body
from evals.Beta.eval_rag import VERSION_KEY, extract_ragas_fields, run_eval_rag
from evals.Beta.run_all import build_report
from modules.content_generator.utils.fslsm_adaptation import build_session_adaptation_contract
from modules.learning_plan_generator.prompts.learning_path_scheduling import learning_path_scheduler_system_prompt


def test_extract_ragas_fields_maps_tutor_trace_into_ragas_row():
    row = extract_ragas_fields(
        {
            "response": "Recursion reduces a problem into smaller subproblems.",
            "retrieval_trace": {
                "contexts": [
                    {
                        "page_content": "Recursion reduces a problem into smaller subproblems.",
                        "source_type": "verified_content",
                        "course_code": "6.0001",
                        "file_name": "lec_1.pdf",
                        "lecture_number": 1,
                    }
                ],
                "tool_calls": [{"tool_name": "retrieve_vector_context", "query": "What is recursion?"}],
            },
        },
        "What is recursion?",
        "Recursion solves a problem by reducing it to smaller versions of itself.",
        case={
            "case_type": "metadata",
            "case_id": "R1",
            "expected_course_code": "6.0001",
            "expected_keywords": ["recursion"],
            "expected_lecture_numbers": [1],
            "ground_truth_facts": ["Recursion reduces a problem to smaller instances."],
        },
    )

    assert row["answer"].startswith("Recursion")
    assert row["contexts"] == ["Recursion reduces a problem into smaller subproblems."]
    assert row["source_course_codes"] == ["6.0001"]
    assert row["source_lecture_numbers"] == [1]


def test_run_eval_rag_marks_missing_contexts_as_error(monkeypatch):
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"response": "Short answer", "profile_updated": False, "retrieval_trace": {"contexts": [], "tool_calls": []}},
            )
        )
        return real_client(transport=transport)

    monkeypatch.setattr("evals.Beta.eval_rag.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr("evals.Beta.eval_rag.httpx.Client", fake_client)

    results = run_eval_rag(
        [
            {
                "goal_id": "G2",
                "learning_goal": "Learn Python",
                "knowledge_point": "Recursion",
                "ground_truth": "Recursion solves problems by breaking them into smaller subproblems.",
                "ground_truth_facts": [],
                "case_type": "metadata",
                "case_id": "R1",
                "expected_course_code": "6.0001",
                "expected_keywords": ["recursion"],
                "query": "What is recursion?",
                "expected_lecture_numbers": [1],
            }
        ],
        base_url="http://test/v1",
    )

    assert results[VERSION_KEY][0]["error"] == "missing_retrieval_contexts"


def test_run_eval_rag_sends_goal_context_and_returns_valid_row(monkeypatch):
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["goal_context"]["course_code"] == "6.0001"
        assert body["goal_context"]["lecture_numbers"] == [1]
        return httpx.Response(
            200,
            json={
                "response": "Variables store values.",
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
                    "tool_calls": [{"tool_name": "prefetch_goal_context_hybrid_filtered", "query": "What is a variable in Python?"}],
                },
            },
        )

    monkeypatch.setattr("evals.Beta.eval_rag.bootstrap_auth_headers", lambda base_url: {"Authorization": "Bearer token"})
    monkeypatch.setattr(
        "evals.Beta.eval_rag.httpx.Client",
        lambda *args, **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )

    results = run_eval_rag(
        [
            {
                "goal_id": "G2",
                "learning_goal": "Learn Python",
                "knowledge_point": "Variables",
                "ground_truth": "Variables store values.",
                "ground_truth_facts": ["Variables store values."],
                "case_type": "metadata",
                "case_id": "R2",
                "expected_course_code": "6.0001",
                "expected_keywords": ["variables"],
                "query": "What is a variable in Python?",
                "expected_lecture_numbers": [1],
            }
        ],
        base_url="http://test/v1",
    )

    assert "error" not in results[VERSION_KEY][0]
    assert results[VERSION_KEY][0]["contexts"] == ["Variables store values."]


def test_build_report_uses_single_backend_format():
    report = build_report(
        {
            VERSION_KEY: {
                "completeness": 4.5,
                "scenario_count": 2,
                "scored_scenario_count": 2,
                "error_count": 0,
                "category_metadata": {"current_product_note": "skill gap note", "mvp_change_note": "skill gap change"},
                "metric_metadata": {"completeness": {"comparable_to_mvp": "partial", "assessment_change_vs_mvp": "new", "assessment_change_reason": "why"}},
            }
        },
        {
            VERSION_KEY: {
                "pedagogical_sequencing": 4.0,
                "scenario_count": 2,
                "scored_scenario_count": 2,
                "not_applicable_zero_gap_count": 0,
                "error_count": 0,
                "deterministic_plan_audit": {"total_violation_count": 1, "total_coverage_gap_count": 0, "scenarios_with_violations": 1, "scenarios_with_coverage_gaps": 0, "scenarios_with_flag_inconsistencies": 0},
                "category_metadata": {"current_product_note": "plan note", "mvp_change_note": "plan change"},
                "metric_metadata": {"pedagogical_sequencing": {"comparable_to_mvp": "partial", "assessment_change_vs_mvp": "new", "assessment_change_reason": "why"}},
            }
        },
        {
            VERSION_KEY: {
                "cognitive_level_match": 4.2,
                "scenario_count": 2,
                "scored_scenario_count": 2,
                "not_applicable_zero_gap_count": 0,
                "error_count": 0,
                "category_metadata": {"current_product_note": "content note", "mvp_change_note": "content change"},
                "metric_metadata": {"cognitive_level_match": {"comparable_to_mvp": "yes", "assessment_change_vs_mvp": "same", "assessment_change_reason": "why"}},
            }
        },
        {VERSION_KEY: {"summary": {"identify_skill_gap": {"p50_ms": 10.0, "p95_ms": 20.0, "error_rate_pct": 0.0, "applicable_count": 2, "skipped_count": 0}}}},
        {
            VERSION_KEY: {
                "context_precision": 0.7,
                "category_metadata": {"current_product_note": "rag note", "mvp_change_note": "rag change"},
                "metric_metadata": {"context_precision": {"comparable_to_mvp": "no", "assessment_change_vs_mvp": "different", "assessment_change_reason": "why"}},
            }
        },
        "2026-03-12 12:00:00",
    )

    assert "GenMentor" not in report
    assert "Delta" not in report
    assert "ablation" not in report.lower()
    assert "scenario_count" in report
    assert "Assessment changed vs MVP" in report
    assert "Bridge Comparison to MVP" in report
    assert "Comparable to MVP?" in report


def test_plan_eval_caps_scores_when_deterministic_audit_finds_skip(monkeypatch):
    scenario = {"id": "S1", "learning_goal": "Learn Python", "learner_information": "I am new to programming."}
    sg_body = {"skill_gaps": [{"name": "Functions", "is_gap": True, "required_level": "advanced", "current_level": "unlearned"}]}
    profile_body = {
        "cognitive_status": {
            "in_progress_skills": [
                {"name": "Functions", "current_proficiency_level": "unlearned", "required_proficiency_level": "advanced"}
            ]
        },
        "learning_preferences": {"fslsm_dimensions": {"fslsm_processing": -0.8}},
    }
    path_body = {
        "learning_path": [
            {
                "id": "Session 1",
                "title": "Jump to Advanced Functions",
                "abstract": "A quick overview of advanced functions.",
                "desired_outcome_when_completed": [{"name": "Functions", "level": "advanced"}],
                "has_checkpoint_challenges": False,
                "thinking_time_buffer_minutes": 0,
                "session_sequence_hint": "application-first",
                "input_mode_hint": "visual",
            }
        ]
    }
    monkeypatch.setattr(
        "evals.Beta.eval_plan.judge",
        lambda *args, **kwargs: {
            "pedagogical_sequencing": {"score": 5, "reason": "Looks well ordered."},
            "skill_coverage": {"score": 5, "reason": "Looks complete."},
            "scope_appropriateness": {"score": 4, "reason": "good"},
            "session_abstraction_quality": {"score": 5, "reason": "good"},
            "fslsm_structural_alignment": {"score": 5, "reason": "good"},
            "solo_outcome_progression": {"score": 5, "reason": "good"},
        },
    )

    result = _evaluate_plan_outputs(scenario, sg_body, profile_body, path_body)

    assert result["scores"]["pedagogical_sequencing"]["score"] == 2
    assert result["scores"]["solo_outcome_progression"]["score"] == 2
    assert result["scores"]["fslsm_structural_alignment"]["score"] == 3
    assert result["pipeline_outputs"]["plan_audit"]["violation_count"] == 1


def test_plan_eval_caps_single_minor_coverage_gap_at_three(monkeypatch):
    scenario = {"id": "S1", "learning_goal": "Learn web development", "learner_information": "I am new to programming."}
    sg_body = {
        "skill_gaps": [
            {"name": "RESTful API Development", "is_gap": True, "required_level": "intermediate", "current_level": "unlearned"}
        ]
    }
    profile_body = {
        "cognitive_status": {
            "in_progress_skills": [
                {
                    "name": "RESTful API Development",
                    "current_proficiency_level": "unlearned",
                    "required_proficiency_level": "intermediate",
                }
            ]
        },
        "learning_preferences": {"fslsm_dimensions": {"fslsm_processing": 0.0}},
    }
    path_body = {
        "learning_path": [
            {
                "id": "Session 1",
                "title": "REST APIs Basics",
                "abstract": "Learn the basic ideas behind REST APIs through clear examples.",
                "desired_outcome_when_completed": [{"name": "RESTful API Development", "level": "beginner"}],
                "has_checkpoint_challenges": False,
                "thinking_time_buffer_minutes": 0,
                "session_sequence_hint": None,
                "input_mode_hint": "mixed",
            }
        ]
    }
    monkeypatch.setattr(
        "evals.Beta.eval_plan.judge",
        lambda *args, **kwargs: {
            "pedagogical_sequencing": {"score": 4, "reason": "Looks well ordered."},
            "skill_coverage": {"score": 5, "reason": "Looks complete."},
            "scope_appropriateness": {"score": 4, "reason": "good"},
            "session_abstraction_quality": {"score": 4, "reason": "good"},
            "fslsm_structural_alignment": {"score": 4, "reason": "good"},
            "solo_outcome_progression": {"score": 4, "reason": "good"},
        },
    )

    result = _evaluate_plan_outputs(scenario, sg_body, profile_body, path_body)

    assert result["pipeline_outputs"]["plan_audit"]["coverage_gap_count"] == 1
    assert result["scores"]["skill_coverage"]["score"] == 3
    assert "one progression coverage gap remains" in result["scores"]["skill_coverage"]["reason"]


def test_planner_prompt_instructs_coverage_first_abstracts():
    assert "Abstract Priority" in learning_path_scheduler_system_prompt
    assert "what the session covers" in learning_path_scheduler_system_prompt.lower()
    assert "the structured fields control downstream delivery" in learning_path_scheduler_system_prompt.lower()
    assert "Bad pattern" in learning_path_scheduler_system_prompt


def test_session_adaptation_contract_ignores_abstract_wording():
    learner_profile = {
        "learning_preferences": {
            "fslsm_dimensions": {
                "fslsm_processing": -0.8,
                "fslsm_perception": -0.8,
                "fslsm_input": -0.8,
                "fslsm_understanding": 0.0,
            }
        }
    }
    session_a = {
        "title": "Functions",
        "abstract": "Learn Python functions, practice simple function calls, with a brief visual walkthrough and checkpoint.",
        "has_checkpoint_challenges": True,
        "thinking_time_buffer_minutes": 0,
        "session_sequence_hint": "application-first",
        "input_mode_hint": "visual",
        "navigation_mode": "linear",
    }
    session_b = {
        **session_a,
        "abstract": "Visual walkthrough with checkpoint challenge and diagrams.",
    }

    assert build_session_adaptation_contract(session_a, learner_profile) == build_session_adaptation_contract(session_b, learner_profile)


def test_brief_visual_and_application_cues_pass_flag_consistency(monkeypatch):
    scenario = {"id": "S1", "learning_goal": "Learn Python", "learner_information": "I am new to programming."}
    sg_body = {"skill_gaps": [{"name": "Functions", "is_gap": True, "required_level": "beginner", "current_level": "unlearned"}]}
    profile_body = {
        "cognitive_status": {
            "in_progress_skills": [
                {"name": "Functions", "current_proficiency_level": "unlearned", "required_proficiency_level": "beginner"}
            ]
        },
        "learning_preferences": {"fslsm_dimensions": {"fslsm_processing": -0.8, "fslsm_input": -0.8}},
    }
    path_body = {
        "learning_path": [
            {
                "id": "Session 1",
                "title": "Functions Basics",
                "abstract": "Learn Python functions by starting with a small coding task, then explain the core idea with a brief visual walkthrough and checkpoint challenge.",
                "desired_outcome_when_completed": [{"name": "Functions", "level": "beginner"}],
                "has_checkpoint_challenges": True,
                "thinking_time_buffer_minutes": 0,
                "session_sequence_hint": "application-first",
                "input_mode_hint": "visual",
            }
        ]
    }
    monkeypatch.setattr(
        "evals.Beta.eval_plan.judge",
        lambda *args, **kwargs: {
            "pedagogical_sequencing": {"score": 4, "reason": "good"},
            "skill_coverage": {"score": 4, "reason": "good"},
            "scope_appropriateness": {"score": 4, "reason": "good"},
            "session_abstraction_quality": {"score": 4, "reason": "good"},
            "fslsm_structural_alignment": {"score": 4, "reason": "good"},
            "solo_outcome_progression": {"score": 4, "reason": "good"},
        },
    )

    result = _evaluate_plan_outputs(scenario, sg_body, profile_body, path_body)

    assert result["pipeline_outputs"]["fslsm_flag_signals"]["issue_count"] == 0


def test_skill_gap_eval_includes_prompt_aligned_evidence(monkeypatch):
    monkeypatch.setattr(
        "evals.Beta.eval_skill_gap.judge",
        lambda *args, **kwargs: {
            "completeness": {"score": 4, "reason": "good"},
            "gap_calibration": {"score": 4, "reason": "good"},
            "goal_refinement_quality": {"score": 3, "reason": "delivery wording present"},
            "confidence_validity": {"score": 4, "reason": "good"},
            "expert_calibration": {"score": 4, "reason": "good"},
            "solo_level_accuracy": {"score": 4, "reason": "good"},
        },
    )
    result = _evaluate_skill_gap_body(
        {"id": "S1", "learning_goal": "Learn Python", "learner_information": "I am new to programming."},
        {
            "skill_requirements": [{"name": "Functions", "required_level": "beginner"}],
            "skill_gaps": [{"name": "Functions", "current_level": "unlearned", "required_level": "beginner"}],
            "goal_assessment": {"requires_retrieval": True, "is_vague": False},
            "goal_context": {"course_code": "6.0001"},
            "retrieved_sources": [{"source_type": "verified_content", "course_code": "6.0001"}],
            "refined_goal": "Learn Python with videos",
        },
    )

    assert result["raw_output"]["goal_assessment"]["requires_retrieval"] is True
    assert result["raw_output"]["retrieved_source_summary"]["retrieved_source_count"] == 1


def test_skill_gap_completeness_rubric_no_longer_treats_single_major_omission_as_one():
    from evals.Beta.eval_skill_gap import SHARED_JUDGE_USER

    completeness_section = SHARED_JUDGE_USER.split("- completeness:", 1)[1].split("- gap_calibration:", 1)[0]

    assert "Score 2: one clearly major skill area is missing" in completeness_section
    assert "Score 1: multiple major skill areas" in completeness_section


def test_content_eval_includes_contract_evidence(monkeypatch):
    monkeypatch.setattr(
        "evals.Beta.eval_content.judge",
        lambda *args, **kwargs: {
            "cognitive_level_match": {"score": 4, "reason": "good"},
            "factual_accuracy": {"score": 4, "reason": "good"},
            "quiz_alignment": {"score": 4, "reason": "good"},
            "engagement_quality": {"score": 4, "reason": "good"},
            "fslsm_content_adaptation": {"score": 4, "reason": "good"},
            "solo_cognitive_alignment": {"score": 4, "reason": "good"},
        },
    )
    result = _evaluate_content_outputs(
        {"id": "S1", "learning_goal": "Learn Python", "learner_information": "I am new to programming."},
        {"skill_gaps": [{"name": "Variables"}]},
        {
            "learning_preferences": {"fslsm_dimensions": {"fslsm_input": -0.8, "fslsm_processing": -0.8}},
            "cognitive_status": {"in_progress_skills": [{"current_proficiency_level": "beginner"}]},
        },
        {
            "learning_path": [
                {
                    "title": "Session 1",
                    "associated_skills": ["Variables"],
                    "desired_outcome_when_completed": [{"name": "Variables", "level": "beginner"}],
                    "has_checkpoint_challenges": True,
                    "thinking_time_buffer_minutes": 0,
                    "session_sequence_hint": "application-first",
                    "input_mode_hint": "visual",
                    "navigation_mode": "linear",
                }
            ]
        },
        {
            "document": "## Variables\nCheckpoint Challenge\n|A|B|\n|---|---|\nVisual explanation.",
            "quizzes": {"single_choice_questions": [{"question": "q"}], "open_ended_questions": []},
        },
    )

    assert result["pipeline_outputs"]["session_adaptation_contract"]
    assert result["pipeline_outputs"]["quiz_counts"]["single_choice_questions"] == 1
    assert result["pipeline_outputs"]["content_contract_signals"]["has_checkpoint_challenge"] is True
