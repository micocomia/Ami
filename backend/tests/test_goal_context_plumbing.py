"""Tests for internal goal_context plumbing across orchestrators."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_schedule_learning_path_with_llm_accepts_goal_context():
    from modules.learning_plan_generator.agents.learning_path_scheduler import schedule_learning_path_with_llm

    goal_context = {"course_code": "6.0001", "lecture_number": 3}
    llm = MagicMock()

    with patch("modules.learning_plan_generator.agents.learning_path_scheduler.LearningPathScheduler") as MockScheduler:
        MockScheduler.return_value.schedule_session.return_value = {"learning_path": []}
        schedule_learning_path_with_llm(llm, {"learning_goal": "Learn Python"}, 3, goal_context=goal_context)

        call_payload = MockScheduler.return_value.schedule_session.call_args.args[0]
        assert call_payload["goal_context"] == goal_context


def test_reschedule_learning_path_with_llm_accepts_goal_context():
    from modules.learning_plan_generator.agents.learning_path_scheduler import reschedule_learning_path_with_llm

    goal_context = {"course_code": "DTI5902", "content_category": "Lectures"}
    llm = MagicMock()

    with patch("modules.learning_plan_generator.agents.learning_path_scheduler.LearningPathScheduler") as MockScheduler:
        MockScheduler.return_value.reschedule.return_value = {"learning_path": []}
        reschedule_learning_path_with_llm(
            llm,
            learning_path=[],
            learner_profile={"learning_goal": "Learn ML"},
            session_count=4,
            goal_context=goal_context,
        )

        call_payload = MockScheduler.return_value.reschedule.call_args.args[0]
        assert call_payload["goal_context"] == goal_context


def test_schedule_learning_path_agentic_accepts_goal_context():
    from modules.learning_plan_generator.orchestrators.learning_plan_pipeline import schedule_learning_path_agentic

    goal_context = {"course_code": "6.0001", "page_number": 5}
    llm = MagicMock()

    with patch("modules.learning_plan_generator.orchestrators.learning_plan_pipeline.LearningPathScheduler") as MockScheduler, \
         patch("modules.learning_plan_generator.orchestrators.learning_plan_pipeline.create_simulate_feedback_tool") as mock_sim_tool_factory, \
         patch("modules.learning_plan_generator.orchestrators.learning_plan_pipeline._evaluate_plan_quality") as mock_quality:
        MockScheduler.return_value.schedule_session.return_value = {"learning_path": []}
        mock_sim_tool_factory.return_value.invoke.return_value = {"feedback": {}}
        mock_quality.return_value = {"pass": True, "issues": [], "feedback_summary": {}}

        schedule_learning_path_agentic(llm, {"learning_goal": "Learn Python"}, goal_context=goal_context)

        call_payload = MockScheduler.return_value.schedule_session.call_args.args[0]
        assert call_payload["goal_context"] == goal_context


@patch("modules.content_generator.agents.document_quiz_generator.generate_document_quizzes_with_llm")
@patch("modules.content_generator.agents.learning_document_integrator.integrate_learning_document_with_llm")
@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.draft_knowledge_points_with_llm")
@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.explore_knowledge_points_with_llm")
def test_create_learning_content_forwards_goal_context(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_quiz,
):
    from modules.content_generator.agents.learning_content_creator import create_learning_content_with_llm

    mock_explore.return_value = [{"name": "Topic A", "type": "foundational"}]
    mock_draft.return_value = [{"title": "Draft A", "content": "Body"}]
    mock_integrate.return_value = "## Document"
    mock_quiz.return_value = {}

    goal_context = {"course_code": "6.0001", "lecture_number": 1}
    profile = {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": 0.0}}}
    llm = MagicMock()

    create_learning_content_with_llm(
        llm,
        profile,
        {},
        {},
        with_quiz=False,
        use_search=False,
        goal_context=goal_context,
        search_rag_manager=MagicMock(),
    )

    assert mock_draft.call_args.kwargs["goal_context"] == goal_context


@patch("modules.content_generator.agents.document_quiz_generator.generate_document_quizzes_with_llm")
@patch("modules.content_generator.agents.learning_document_integrator.integrate_learning_document_with_llm")
@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.draft_knowledge_points_with_llm")
@patch("modules.content_generator.agents.goal_oriented_knowledge_explorer.explore_knowledge_points_with_llm")
def test_create_learning_content_works_without_goal_context(
    mock_explore,
    mock_draft,
    mock_integrate,
    mock_quiz,
):
    from modules.content_generator.agents.learning_content_creator import create_learning_content_with_llm

    mock_explore.return_value = [{"name": "Topic A", "type": "foundational"}]
    mock_draft.return_value = [{"title": "Draft A", "content": "Body"}]
    mock_integrate.return_value = "## Document"
    mock_quiz.return_value = {}

    profile = {"learning_preferences": {"fslsm_dimensions": {"fslsm_input": 0.0}}}
    llm = MagicMock()

    create_learning_content_with_llm(
        llm,
        profile,
        {},
        {},
        with_quiz=False,
        use_search=False,
        search_rag_manager=MagicMock(),
    )

    assert "goal_context" in mock_draft.call_args.kwargs
    assert mock_draft.call_args.kwargs["goal_context"] is None
