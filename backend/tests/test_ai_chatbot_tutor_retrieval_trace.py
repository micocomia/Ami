import os
import sys
from unittest.mock import MagicMock

from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.ai_chatbot_tutor.agents.ai_chatbot_tutor import AITutorChatbot, chat_with_tutor_with_llm


class _FakeSearchRagManager:
    search_runner = None

    def retrieve(self, query: str, k: int = 5):
        assert "recursion" in query.lower()
        return [
            Document(
                page_content="Recursion solves a problem by reducing it to smaller instances of itself.",
                metadata={
                    "source_type": "verified_content",
                    "course_code": "6.0001",
                    "file_name": "lec_1.pdf",
                    "lecture_number": 1,
                },
            )
        ]

    def invoke_hybrid_filtered(self, query: str, k: int = 5, **kwargs):
        assert query
        assert kwargs["course_code"] == "6.0001"
        return [
            Document(
                page_content="Lecture-grounded recursion content.",
                metadata={
                    "source_type": "verified_content",
                    "course_code": "6.0001",
                    "file_name": "lec_1.pdf",
                    "lecture_number": 1,
                },
            )
        ]

    def invoke_hybrid(self, query: str, k: int = 5):
        return [
            Document(
                page_content="Fallback hybrid recursion content.",
                metadata={
                    "source_type": "verified_content",
                    "course_code": "6.0001",
                    "file_name": "lec_2.pdf",
                    "lecture_number": 2,
                },
            )
        ]


class _FallbackSearchRagManager(_FakeSearchRagManager):
    def invoke_hybrid_filtered(self, query: str, k: int = 5, **kwargs):
        return []


class _NoisyLectureSearchRagManager(_FakeSearchRagManager):
    def invoke_hybrid_filtered(self, query: str, k: int = 5, **kwargs):
        lecture_number = kwargs.get("lecture_number")
        if lecture_number == 3:
            return [
                Document(
                    page_content="GUESS-AND-CHECK is an algorithmic strategy for solving problems by testing candidate solutions.",
                    metadata={
                        "source_type": "verified_content",
                        "course_code": "6.0001",
                        "file_name": "lec_3.pdf",
                        "lecture_number": 3,
                        "content_category": "Lectures",
                    },
                ),
                Document(
                    page_content='EXERCISE s1 = "mit u rock" s2 = "i rule mit" if len(s1) == len(s2): print("common letter")',
                    metadata={
                        "source_type": "verified_content",
                        "course_code": "6.0001",
                        "file_name": "lec_3.pdf",
                        "lecture_number": 3,
                        "content_category": "Lectures",
                    },
                ),
            ]
        if lecture_number == 6:
            return [
                Document(
                    page_content="TOWERS OF HANOI shows recursive problem solving by breaking a problem into smaller versions of itself.",
                    metadata={
                        "source_type": "verified_content",
                        "course_code": "6.0001",
                        "file_name": "lec_6.pdf",
                        "lecture_number": 6,
                        "content_category": "Lectures",
                    },
                ),
                Document(
                    page_content="Fibonacci memoization reduces repeated recursive calls by storing prior results in a dictionary.",
                    metadata={
                        "source_type": "verified_content",
                        "course_code": "6.0001",
                        "file_name": "lec_6.pdf",
                        "lecture_number": 6,
                        "content_category": "Lectures",
                    },
                ),
            ]
        return []


def test_chat_with_tutor_preserves_legacy_plain_string(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        for tool in self._tools:
            if getattr(tool, "name", "") == "retrieve_vector_context":
                tool.invoke({"query": input_vars["latest_user_message"], "top_k": 5, "max_chars": 2800})
        return "A concise recursion answer."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "What is recursion?"}],
        learner_profile="{}",
        search_rag_manager=_FakeSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=False,
    )

    assert result == "A concise recursion answer."


def test_chat_with_tutor_metadata_includes_retrieval_trace(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        for tool in self._tools:
            if getattr(tool, "name", "") == "retrieve_vector_context":
                tool.invoke({"query": input_vars["latest_user_message"], "top_k": 5, "max_chars": 2800})
        return "A concise recursion answer."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "What is recursion?"}],
        learner_profile="{}",
        search_rag_manager=_FakeSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    assert result["response"] == "A concise recursion answer."
    assert result["profile_updated"] is False
    assert result["retrieval_trace"]["tool_calls"][0]["tool_name"] == "retrieve_vector_context"
    assert result["retrieval_trace"]["contexts"][0]["source_type"] == "verified_content"
    assert result["retrieval_trace"]["contexts"][0]["course_code"] == "6.0001"


def test_chat_with_tutor_goal_context_without_retrieval_fields_does_not_prefetch(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        assert input_vars["external_resources"] == ""
        return "No prefetched grounding."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "Explain recursion."}],
        learner_profile="{}",
        goal_context={"is_vague": False},
        search_rag_manager=_FakeSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    assert result["response"] == "No prefetched grounding."
    assert result["retrieval_trace"] == {"contexts": [], "tool_calls": []}


def test_chat_with_tutor_goal_context_prefetches_filtered_retrieval(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        assert "Lecture-grounded recursion content." in input_vars["external_resources"]
        assert '"course_code": "6.0001"' in input_vars["goal_context"]
        return "Grounded recursion answer."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "Explain recursion in 6.0001."}],
        learner_profile="{}",
        goal_context={"course_code": "6.0001", "lecture_numbers": [1]},
        search_rag_manager=_FakeSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    assert result["response"] == "Grounded recursion answer."
    assert result["retrieval_trace"]["contexts"][0]["course_code"] == "6.0001"
    assert result["retrieval_trace"]["tool_calls"][0]["tool_name"] == "prefetch_goal_context_hybrid_filtered"


def test_chat_with_tutor_goal_context_prefetch_falls_back_to_hybrid(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        assert "Fallback hybrid recursion content." in input_vars["external_resources"]
        return "Fallback grounded recursion answer."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "Explain recursion in 6.0001."}],
        learner_profile="{}",
        goal_context={"course_code": "6.0001"},
        search_rag_manager=_FallbackSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    tool_names = [item["tool_name"] for item in result["retrieval_trace"]["tool_calls"]]
    assert "prefetch_goal_context_hybrid_filtered" in tool_names
    assert "prefetch_goal_context_hybrid" in tool_names
    assert result["retrieval_trace"]["contexts"][0]["file_name"] == "lec_2.pdf"


def test_chat_with_tutor_goal_context_prefetch_filters_noisy_chunks(monkeypatch):
    def fake_invoke(self, input_vars, task_prompt=None):
        assert "GUESS-AND-CHECK" in input_vars["external_resources"]
        assert "TOWERS OF HANOI" in input_vars["external_resources"]
        assert 'mit u rock' not in input_vars["external_resources"]
        return "Grounded computational thinking answer."

    monkeypatch.setattr(AITutorChatbot, "invoke", fake_invoke)

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "Using MIT 6.0001 lectures, teach computational thinking and algorithmic problem solving in Python"}],
        learner_profile='{"learning_goal":"I want to review computational problem-solving from MIT 6.0001 lectures"}',
        goal_context={"course_code": "6.0001", "lecture_numbers": [3, 6], "content_category": "Lectures"},
        search_rag_manager=_NoisyLectureSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    contexts = result["retrieval_trace"]["contexts"]
    page_contents = [item["page_content"] for item in contexts]
    assert all("mit u rock" not in text for text in page_contents)


def test_chat_with_tutor_goal_context_prefetch_keeps_lecture_diversity(monkeypatch):
    monkeypatch.setattr(AITutorChatbot, "invoke", lambda self, input_vars, task_prompt=None: "Grounded computational thinking answer.")

    result = chat_with_tutor_with_llm(
        MagicMock(),
        messages=[{"role": "user", "content": "Using MIT 6.0001 lectures, teach computational thinking and algorithmic problem solving in Python"}],
        learner_profile='{"learning_goal":"I want to review computational problem-solving from MIT 6.0001 lectures"}',
        goal_context={"course_code": "6.0001", "lecture_numbers": [3, 6], "content_category": "Lectures"},
        search_rag_manager=_NoisyLectureSearchRagManager(),
        use_vector_retrieval=True,
        use_web_search=False,
        use_media_search=False,
        allow_preference_updates=False,
        return_metadata=True,
    )

    lecture_numbers = {item["lecture_number"] for item in result["retrieval_trace"]["contexts"]}
    assert 3 in lecture_numbers
    assert 6 in lecture_numbers
