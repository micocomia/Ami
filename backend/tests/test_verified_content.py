"""Tests for verified course content loading, indexing, and hybrid retrieval."""

import os
import json
import shutil
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.documents import Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_course_dir(base, code, name, term, categories=None):
    """Create a fake course directory structure for testing."""
    folder_name = f"{code}_{name}_{term}"
    course_dir = os.path.join(base, folder_name)
    os.makedirs(course_dir, exist_ok=True)
    categories = categories or ["Syllabus", "Lectures", "References"]
    for cat in categories:
        os.makedirs(os.path.join(course_dir, cat), exist_ok=True)
    return course_dir


def _write_json(path, title="Test Syllabus", content="This is the syllabus content."):
    with open(path, "w") as f:
        json.dump({"title": title, "content": content}, f)


def _write_text(path, content="print('hello world')"):
    with open(path, "w") as f:
        f.write(content)


# ===========================================================================
# TestVerifiedContentLoader
# ===========================================================================


class TestVerifiedContentLoader:

    def test_scan_courses_finds_all_courses(self, tmp_path):
        from base.verified_content_loader import scan_courses

        _make_course_dir(str(tmp_path), "6.0001", "intro-to-cs", "fall-2016")
        _make_course_dir(str(tmp_path), "11.437", "financing-econ", "fall-2016")
        _make_course_dir(str(tmp_path), "6.831", "ui-design", "spring-2011")

        courses = scan_courses(str(tmp_path))
        assert len(courses) == 3
        codes = {c["course_code"] for c in courses}
        assert codes == {"6.0001", "11.437", "6.831"}
        for c in courses:
            assert "course_name" in c
            assert "term" in c
            assert "directory" in c

    def test_scan_courses_empty_dir(self, tmp_path):
        from base.verified_content_loader import scan_courses

        courses = scan_courses(str(tmp_path))
        assert courses == []

    def test_load_file_json(self, tmp_path):
        from base.verified_content_loader import load_file

        json_path = os.path.join(str(tmp_path), "syllabus.json")
        _write_json(json_path, title="Course Syllabus", content="Course overview text here.")

        docs = load_file(json_path)
        assert len(docs) == 1
        assert "Course overview text here." in docs[0].page_content
        assert docs[0].metadata.get("title") == "Course Syllabus"

    def test_load_file_text(self, tmp_path):
        from base.verified_content_loader import load_file

        py_path = os.path.join(str(tmp_path), "example.py")
        _write_text(py_path, "x = 42\nprint(x)")

        docs = load_file(py_path)
        assert len(docs) == 1
        assert "x = 42" in docs[0].page_content

    def test_load_file_unsupported_skipped(self, tmp_path):
        from base.verified_content_loader import load_file

        ds_store = os.path.join(str(tmp_path), ".DS_Store")
        _write_text(ds_store, "binary junk")

        keep = os.path.join(str(tmp_path), ".keep")
        _write_text(keep, "")

        assert load_file(ds_store) == []
        assert load_file(keep) == []

    def test_extract_lecture_number(self):
        from base.verified_content_loader import _extract_lecture_number

        # Pattern: Lec_N.pdf
        assert _extract_lecture_number("Lec_1.pdf") == 1
        assert _extract_lecture_number("Lec_12.pdf") == 12

        # Pattern: ...LecN.pdf (no underscore)
        assert _extract_lecture_number("MIT11_437F16_Lec3.pdf") == 3

        # Pattern: ...lecNN.pdf (lowercase)
        assert _extract_lecture_number("MIT6_831S11_lec01.pdf") == 1

        # Non-lecture files
        assert _extract_lecture_number("syllabus.json") is None
        assert _extract_lecture_number("data.json") is None
        assert _extract_lecture_number("code.py") is None

    def test_load_course_documents_has_metadata(self, tmp_path):
        from base.verified_content_loader import load_course_documents

        course_dir = _make_course_dir(str(tmp_path), "6.0001", "intro-cs", "fall-2016")
        _write_json(
            os.path.join(course_dir, "Syllabus", "data.json"),
            title="Syllabus",
            content="Welcome to the course.",
        )
        _write_text(
            os.path.join(course_dir, "References", "lec1.py"),
            "# Lecture 1 code\nprint('hello')",
        )

        metadata = {
            "course_code": "6.0001",
            "course_name": "intro cs",
            "term": "fall 2016",
            "directory": course_dir,
        }
        docs = load_course_documents(course_dir, metadata)
        assert len(docs) >= 2

        required_keys = {"source_type", "course_code", "course_name", "term", "content_category", "file_name", "lecture_number"}
        for doc in docs:
            assert required_keys.issubset(doc.metadata.keys()), f"Missing keys in {doc.metadata}"
            assert doc.metadata["source_type"] == "verified_content"
            assert doc.metadata["course_code"] == "6.0001"

    def test_lecture_number_in_metadata(self, tmp_path):
        from base.verified_content_loader import load_course_documents

        course_dir = _make_course_dir(str(tmp_path), "6.0001", "intro-cs", "fall-2016")
        # Lecture file — should get lecture_number
        _write_text(
            os.path.join(course_dir, "Lectures", "Lec_8.py"),
            "# Lecture 8 content",
        )
        # Non-lecture file — should get lecture_number: None
        _write_json(
            os.path.join(course_dir, "Syllabus", "data.json"),
            title="Syllabus",
            content="Course syllabus.",
        )

        metadata = {
            "course_code": "6.0001",
            "course_name": "intro cs",
            "term": "fall 2016",
            "directory": course_dir,
        }
        docs = load_course_documents(course_dir, metadata)

        lecture_docs = [d for d in docs if d.metadata["file_name"] == "Lec_8.py"]
        assert len(lecture_docs) == 1
        assert lecture_docs[0].metadata["lecture_number"] == 8

        syllabus_docs = [d for d in docs if d.metadata["file_name"] == "data.json"]
        assert len(syllabus_docs) == 1
        assert syllabus_docs[0].metadata["lecture_number"] is None


# ===========================================================================
# TestVerifiedContentManager
# ===========================================================================


class TestVerifiedContentManager:

    @pytest.fixture
    def mock_embedder(self):
        embedder = MagicMock()
        embedder.embed_documents.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
        embedder.embed_query.return_value = [0.1] * 384
        return embedder

    @pytest.fixture
    def manager(self, mock_embedder, tmp_path):
        from base.verified_content_manager import VerifiedContentManager
        from base.rag_factory import TextSplitterFactory

        text_splitter = TextSplitterFactory.create(
            splitter_type="recursive_character",
            chunk_size=500,
            chunk_overlap=0,
        )
        return VerifiedContentManager(
            embedder=mock_embedder,
            text_splitter=text_splitter,
            persist_directory=str(tmp_path / "vs"),
            collection_name="test_verified",
        )

    def test_from_config_creates_manager(self):
        from base.verified_content_manager import VerifiedContentManager

        config = {
            "embedder": {"model_name": "sentence-transformers/all-mpnet-base-v2", "provider": "huggingface"},
            "rag": {"chunk_size": 500},
            "vectorstore": {"persist_directory": "./data/vectorstore"},
            "verified_content": {"collection_name": "test_vc"},
        }
        mgr = VerifiedContentManager.from_config(config)
        assert mgr is not None
        assert mgr.collection_name == "test_vc"

    def test_index_and_retrieve(self, manager, tmp_path):
        # Create a mini course structure
        content_dir = tmp_path / "courses"
        course_dir = _make_course_dir(str(content_dir), "TEST", "course", "2024")
        _write_json(
            os.path.join(course_dir, "Syllabus", "data.json"),
            title="Test",
            content="Python programming fundamentals including variables, loops, and functions.",
        )
        _write_text(
            os.path.join(course_dir, "References", "code.py"),
            "def hello():\n    print('Hello World')\n",
        )

        count = manager.index_verified_content(str(content_dir))
        assert count > 0

        results = manager.retrieve("Python programming")
        assert len(results) > 0
        assert any("source_type" in doc.metadata for doc in results)

    def test_index_skips_if_already_indexed(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        course_dir = _make_course_dir(str(content_dir), "TEST", "course", "2024")
        _write_json(
            os.path.join(course_dir, "Syllabus", "data.json"),
            content="Some content for indexing.",
        )

        count1 = manager.index_verified_content(str(content_dir))
        assert count1 > 0

        count2 = manager.index_verified_content(str(content_dir))
        assert count2 == count1  # Should skip, return same count

    def test_retrieve_empty_collection(self, manager):
        results = manager.retrieve("anything")
        assert results == []

    def test_list_courses(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        _make_course_dir(str(content_dir), "CS101", "intro", "fall-2024")
        _make_course_dir(str(content_dir), "CS201", "advanced", "spring-2025")

        courses = manager.list_courses(str(content_dir))
        assert len(courses) == 2
        codes = {c["course_code"] for c in courses}
        assert codes == {"CS101", "CS201"}

    def test_sync_skips_when_manifest_unchanged(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        course_dir = _make_course_dir(str(content_dir), "TEST", "course", "2024")
        _write_text(
            os.path.join(course_dir, "Lectures", "Lec_4.py"),
            "def topic_four():\n    return 'loops and complexity'\n",
        )

        manifest = manager._build_manifest(str(content_dir))
        manager._save_manifest(manifest)

        manager.vectorstore = MagicMock()
        manager.vectorstore._collection.count.return_value = 7

        with patch.object(manager, "index_verified_content") as mock_index, patch.object(manager, "_clear_collection") as mock_clear:
            result = manager.sync_verified_content(str(content_dir))

        assert result["reindexed"] is False
        assert result["reason"] == "unchanged"
        mock_clear.assert_not_called()
        mock_index.assert_not_called()

    def test_sync_reindexes_when_manifest_changed(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        course_dir = _make_course_dir(str(content_dir), "TEST", "course", "2024")
        lecture_file = os.path.join(course_dir, "Lectures", "Lec_4.py")
        _write_text(
            lecture_file,
            "def topic_four():\n    return 'version-one'\n",
        )

        manifest = manager._build_manifest(str(content_dir))
        manager._save_manifest(manifest)

        # Update file contents to trigger manifest hash change.
        _write_text(
            lecture_file,
            "def topic_four():\n    return 'version-two'\n",
        )

        manager.vectorstore = MagicMock()
        manager.vectorstore._collection.count.return_value = 7

        with patch.object(manager, "_clear_collection") as mock_clear, patch.object(
            manager, "index_verified_content", return_value=11
        ) as mock_index:
            result = manager.sync_verified_content(str(content_dir))

        assert result["reindexed"] is True
        assert result["reason"] == "manifest_changed"
        mock_clear.assert_called_once()
        mock_index.assert_called_once_with(str(content_dir))

    def test_sync_reindexes_when_manifest_missing(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        course_dir = _make_course_dir(str(content_dir), "TEST", "course", "2024")
        _write_json(
            os.path.join(course_dir, "Syllabus", "syllabus.json"),
            title="Test Syllabus",
            content="Course content.",
        )

        manager.vectorstore = MagicMock()
        manager.vectorstore._collection.count.return_value = 5

        with patch.object(manager, "_clear_collection") as mock_clear, patch.object(
            manager, "index_verified_content", return_value=9
        ) as mock_index:
            result = manager.sync_verified_content(str(content_dir))

        assert result["reindexed"] is True
        assert result["reason"] == "missing_manifest"
        mock_clear.assert_called_once()
        mock_index.assert_called_once_with(str(content_dir))


# ===========================================================================
# TestHybridRetrieval
# ===========================================================================


class TestHybridRetrieval:

    def _make_docs(self, source_type, count):
        return [
            Document(
                page_content=f"Content {i} from {source_type}",
                metadata={"source_type": source_type},
            )
            for i in range(count)
        ]

    def test_invoke_hybrid_verified_only(self):
        """Verified >= k results, web search NOT called."""
        from base.search_rag import SearchRagManager

        verified_docs = self._make_docs("verified_content", 5)

        mock_vcm = MagicMock()
        mock_vcm.retrieve.return_value = verified_docs

        manager = SearchRagManager(
            embedder=MagicMock(),
            verified_content_manager=mock_vcm,
        )
        manager.invoke = MagicMock()  # Should NOT be called

        results = manager.invoke_hybrid("test query", k=5)
        assert len(results) == 5
        assert all(d.metadata["source_type"] == "verified_content" for d in results)
        manager.invoke.assert_not_called()

    def test_invoke_hybrid_falls_back_to_web(self):
        """Verified < k, web called, verified docs first."""
        from base.search_rag import SearchRagManager

        verified_docs = self._make_docs("verified_content", 2)
        web_docs = self._make_docs("web_search", 5)

        mock_vcm = MagicMock()
        mock_vcm.retrieve.return_value = verified_docs

        manager = SearchRagManager(
            embedder=MagicMock(),
            verified_content_manager=mock_vcm,
        )
        manager.invoke = MagicMock(return_value=web_docs)

        results = manager.invoke_hybrid("test query", k=5)
        assert len(results) == 5
        # Verified docs come first
        assert results[0].metadata["source_type"] == "verified_content"
        assert results[1].metadata["source_type"] == "verified_content"
        # Web docs fill the remaining slots
        assert results[2].metadata["source_type"] == "web_search"
        manager.invoke.assert_called_once()

    def test_invoke_hybrid_no_verified_manager(self):
        """Falls back to web entirely when no verified_content_manager."""
        from base.search_rag import SearchRagManager

        web_docs = self._make_docs("web_search", 5)

        manager = SearchRagManager(
            embedder=MagicMock(),
            verified_content_manager=None,
        )
        manager.invoke = MagicMock(return_value=web_docs)

        results = manager.invoke_hybrid("test query", k=5)
        assert len(results) == 5
        assert all(d.metadata["source_type"] == "web_search" for d in results)

    def test_invoke_hybrid_source_types_preserved(self):
        """Source types are preserved in returned docs."""
        from base.search_rag import SearchRagManager

        verified_docs = self._make_docs("verified_content", 3)
        web_docs = self._make_docs("web_search", 3)

        mock_vcm = MagicMock()
        mock_vcm.retrieve.return_value = verified_docs

        manager = SearchRagManager(
            embedder=MagicMock(),
            verified_content_manager=mock_vcm,
        )
        manager.invoke = MagicMock(return_value=web_docs)

        results = manager.invoke_hybrid("test query", k=5)
        source_types = {d.metadata["source_type"] for d in results}
        assert "verified_content" in source_types
        assert "web_search" in source_types
