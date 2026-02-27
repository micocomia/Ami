"""Tests for internal goal_context plumbing across orchestrators."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


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
         patch("modules.learning_plan_generator.orchestrators.learning_plan_pipeline.create_simulate_feedback_tool") as mock_sim_tool_factory:
        MockScheduler.return_value.schedule_session.return_value = {"learning_path": []}
        mock_sim_tool_factory.return_value.invoke.return_value = {
            "feedback": {"progression": "", "engagement": "", "personalization": ""},
            "suggestions": {"progression": "", "engagement": "", "personalization": ""},
            "is_acceptable": True,
            "issues": [],
            "improvement_directives": "",
        }

        schedule_learning_path_agentic(llm, {"learning_goal": "Learn Python"}, goal_context=goal_context)

        call_payload = MockScheduler.return_value.schedule_session.call_args.args[0]
        assert call_payload["goal_context"] == goal_context


@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
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


@patch("modules.content_generator.orchestrators.content_generation_pipeline.generate_document_quizzes_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.integrate_learning_document_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.draft_knowledge_points_with_llm")
@patch("modules.content_generator.orchestrators.content_generation_pipeline.explore_knowledge_points_with_llm")
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


@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.SearchEnhancedKnowledgeDrafter.invoke")
def test_drafter_skips_retrieval_when_goal_context_empty(mock_invoke):
    from modules.content_generator.agents.search_enhanced_knowledge_drafter import SearchEnhancedKnowledgeDrafter

    mock_invoke.return_value = {"title": "Draft", "content": "Body"}
    rag = MagicMock()
    rag.max_retrieval_results = 5
    drafter = SearchEnhancedKnowledgeDrafter(MagicMock(), search_rag_manager=rag, use_search=True)

    result = drafter.draft(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Intro"},
            "knowledge_points": [{"name": "Variables"}],
            "knowledge_point": {"name": "Variables", "type": "foundational"},
            "goal_context": {},
        }
    )

    assert "retrieval_queries" not in result
    rag.invoke_hybrid.assert_not_called()
    rag.invoke_hybrid_filtered.assert_not_called()


@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.SearchEnhancedKnowledgeDrafter.invoke")
def test_drafter_retrieves_when_goal_context_present(mock_invoke):
    from modules.content_generator.agents.search_enhanced_knowledge_drafter import SearchEnhancedKnowledgeDrafter

    mock_invoke.return_value = {"title": "Draft", "content": "Body"}
    rag = MagicMock()
    rag.max_retrieval_results = 5
    rag.invoke_hybrid_filtered.return_value = []
    drafter = SearchEnhancedKnowledgeDrafter(MagicMock(), search_rag_manager=rag, use_search=True)

    result = drafter.draft(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Intro"},
            "knowledge_points": [{"name": "Variables"}],
            "knowledge_point": {"name": "Variables", "type": "foundational"},
            "goal_context": {"course_code": "DTI5902"},
        }
    )

    assert "retrieval_queries" in result
    rag.invoke_hybrid_filtered.assert_called()
    _, kwargs = rag.invoke_hybrid_filtered.call_args
    assert kwargs["course_code"] == "DTI5902"


@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.SearchEnhancedKnowledgeDrafter.invoke")
def test_drafter_skips_retrieval_when_goal_context_has_no_retrieval_fields(mock_invoke):
    from modules.content_generator.agents.search_enhanced_knowledge_drafter import SearchEnhancedKnowledgeDrafter

    mock_invoke.return_value = {"title": "Draft", "content": "Body"}
    rag = MagicMock()
    rag.max_retrieval_results = 5
    drafter = SearchEnhancedKnowledgeDrafter(MagicMock(), search_rag_manager=rag, use_search=True)

    result = drafter.draft(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Intro"},
            "knowledge_points": [{"name": "Variables"}],
            "knowledge_point": {"name": "Variables", "type": "foundational"},
            "goal_context": {"is_vague": False},
        }
    )

    assert "retrieval_queries" not in result
    rag.invoke_hybrid.assert_not_called()
    rag.invoke_hybrid_filtered.assert_not_called()


@patch("modules.content_generator.agents.search_enhanced_knowledge_drafter.SearchEnhancedKnowledgeDrafter.invoke")
def test_drafter_falls_back_when_filtered_retrieval_empty(mock_invoke):
    from modules.content_generator.agents.search_enhanced_knowledge_drafter import SearchEnhancedKnowledgeDrafter

    mock_invoke.return_value = {"title": "Draft", "content": "Body"}
    rag = MagicMock()
    rag.max_retrieval_results = 5
    rag.invoke_hybrid_filtered.return_value = []
    rag.invoke_hybrid.return_value = []
    drafter = SearchEnhancedKnowledgeDrafter(MagicMock(), search_rag_manager=rag, use_search=True)

    drafter.draft(
        {
            "learner_profile": {},
            "learning_path": {},
            "learning_session": {"title": "Intro"},
            "knowledge_points": [{"name": "Variables"}],
            "knowledge_point": {"name": "Variables", "type": "foundational"},
            "goal_context": {"course_code": "DTI5902"},
        }
    )

    rag.invoke_hybrid_filtered.assert_called()
    rag.invoke_hybrid.assert_called()


def test_generate_learning_content_endpoint_forwards_goal_context():
    from main import app

    payload = {
        "learner_profile": "{}",
        "learning_path": "{}",
        "learning_session": "{}",
        "use_search": True,
        "allow_parallel": True,
        "with_quiz": False,
        "method_name": "ami",
        "goal_context": {"course_code": "DTI5902", "lecture_numbers": [1, 2]},
    }

    with patch("main.get_llm", return_value=MagicMock()), \
         patch("main.generate_learning_content_with_llm") as mock_create:
        mock_create.return_value = {"document": "ok"}
        client = TestClient(app)
        response = client.post("/generate-learning-content", json=payload)

    assert response.status_code == 200
    assert response.json()["document"] == "ok"
    assert "view_model" in response.json()
    assert mock_create.call_args.kwargs["goal_context"] == payload["goal_context"]


def test_generate_learning_content_rejects_non_ami_method():
    from main import app

    payload = {
        "learner_profile": "{}",
        "learning_path": "{}",
        "learning_session": "{}",
        "method_name": "genmentor",
    }
    client = TestClient(app)
    response = client.post("/generate-learning-content", json=payload)
    assert response.status_code == 400


def test_removed_content_generation_endpoints_return_404():
    from main import app

    client = TestClient(app)
    for endpoint in (
        "/explore-knowledge-points",
        "/draft-knowledge-points",
        "/integrate-learning-document",
        "/generate-document-quizzes",
        "/tailor-knowledge-content",
    ):
        assert client.post(endpoint, json={}).status_code == 404


def test_draft_knowledge_point_endpoint_still_available():
    from main import app

    payload = {
        "learner_profile": "{}",
        "learning_path": "{}",
        "learning_session": "{}",
        "knowledge_points": "[]",
        "knowledge_point": "{}",
        "use_search": False,
    }
    with patch("main.get_llm", return_value=MagicMock()), \
         patch("main.draft_knowledge_point_with_llm", return_value={"title": "Draft", "content": "Body"}):
        client = TestClient(app)
        response = client.post("/draft-knowledge-point", json=payload)
    assert response.status_code == 200
    assert response.json()["knowledge_draft"]["title"] == "Draft"
