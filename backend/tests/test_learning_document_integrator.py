import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@patch("modules.content_generator.agents.learning_document_integrator.LearningDocumentIntegrator.invoke")
def test_integrator_retries_once_when_content_structure_is_invalid(mock_invoke):
    from modules.content_generator.agents.learning_document_integrator import LearningDocumentIntegrator

    mock_invoke.side_effect = [
        {
            "title": "Session Title",
            "overview": "Overview text.",
            "content": "Integrated prose without top-level headings.",
            "summary": "Summary text.",
        },
        {
            "title": "Session Title",
            "overview": "Overview text.",
            "content": "## Section A\n\nInstructional content.",
            "summary": "Summary text.",
        },
    ]

    integrator = LearningDocumentIntegrator(MagicMock())
    output = integrator.integrate(
        {
            "learner_profile": {},
            "learning_path": [],
            "learning_session": {"title": "Session A"},
            "knowledge_points": [{"name": "Section A", "role": "foundational", "solo_level": "beginner"}],
            "knowledge_drafts": [{"title": "Section A", "content": "Draft content."}],
            "session_adaptation_contract": "{}",
            "understanding_hints": "",
            "integration_feedback": "",
        }
    )

    assert mock_invoke.call_count == 2
    second_payload = mock_invoke.call_args_list[1].args[0]
    assert "Structure repair required" in second_payload["integration_feedback"]
    assert output["content"].startswith("## Section A")
