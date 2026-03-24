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

    def test_load_with_azure_di_page_number(self, tmp_path):
        """_load_with_azure_di normalises page_number from Azure DI metadata."""
        from base.verified_content_loader import _load_with_azure_di

        fake_doc = Document(
            page_content="Lecture content page 1",
            metadata={"page_number": 1, "source": "test.pdf"},
        )
        with patch(
            "langchain_community.document_loaders.AzureAIDocumentIntelligenceLoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [fake_doc]
            docs = _load_with_azure_di("/fake/path/test.pdf")

        assert len(docs) == 1
        assert docs[0].metadata["page_number"] == 1
        assert docs[0].page_content == "Lecture content page 1"

    def test_load_with_azure_di_missing_page_number(self, tmp_path):
        """_load_with_azure_di sets page_number to None when absent."""
        from base.verified_content_loader import _load_with_azure_di

        fake_doc = Document(
            page_content="Some content",
            metadata={"source": "test.pdf"},
        )
        with patch(
            "langchain_community.document_loaders.AzureAIDocumentIntelligenceLoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [fake_doc]
            docs = _load_with_azure_di("/fake/path/test.pdf")

        assert docs[0].metadata["page_number"] is None

    def test_load_with_azure_di_uses_page_fallback(self, tmp_path):
        """_load_with_azure_di falls back to `page` when `page_number` is missing."""
        from base.verified_content_loader import _load_with_azure_di

        fake_doc = Document(
            page_content="Some content",
            metadata={"page": 6, "source": "test.pdf"},
        )
        with patch(
            "langchain_community.document_loaders.AzureAIDocumentIntelligenceLoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [fake_doc]
            docs = _load_with_azure_di("/fake/path/test.pdf")

        assert docs[0].metadata["page_number"] == 6

    def test_load_with_azure_di_uses_url_path(self, tmp_path):
        """_load_with_azure_di passes blob SAS URLs via url_path."""
        from base.verified_content_loader import _load_with_azure_di

        fake_doc = Document(
            page_content="PDF page content",
            metadata={"page_number": 1, "source": "https://example/blob.pdf"},
        )
        with patch(
            "langchain_community.document_loaders.AzureAIDocumentIntelligenceLoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [fake_doc]
            docs = _load_with_azure_di(url_path="https://example/blob.pdf?sas-token")

        assert len(docs) == 1
        kwargs = MockLoader.call_args.kwargs
        assert kwargs["url_path"] == "https://example/blob.pdf?sas-token"
        assert "url_source" not in kwargs

    def test_load_with_azure_di_strips_non_primitive_metadata(self, tmp_path):
        """_load_with_azure_di removes complex metadata values before returning."""
        from base.verified_content_loader import _load_with_azure_di

        fake_doc = Document(
            page_content="Content",
            metadata={"page_number": 2, "nested": {"key": "value"}, "items": [1, 2]},
        )
        with patch(
            "langchain_community.document_loaders.AzureAIDocumentIntelligenceLoader"
        ) as MockLoader:
            MockLoader.return_value.load.return_value = [fake_doc]
            docs = _load_with_azure_di("/fake/path/test.pdf")

        assert "nested" not in docs[0].metadata
        assert "items" not in docs[0].metadata
        assert docs[0].metadata["page_number"] == 2


# ===========================================================================
# TestVerifiedContentManager
# ===========================================================================


def _make_blob(name, etag='"0x8ABC"', size=1024, last_modified=None):
    """Create a fake BlobProperties-like object for testing."""
    from datetime import datetime, timezone
    blob = MagicMock()
    blob.name = name
    blob.etag = etag
    blob.size = size
    blob.last_modified = last_modified or datetime(2024, 1, 1, tzinfo=timezone.utc)
    return blob


class TestVerifiedContentManager:

    @pytest.fixture
    def mock_embedder(self):
        embedder = MagicMock()
        embedder.embed_documents.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
        embedder.embed_query.return_value = [0.1] * 384
        return embedder

    @pytest.fixture
    def manager(self, mock_embedder):
        from base.verified_content_manager import VerifiedContentManager
        from base.rag_factory import TextSplitterFactory

        text_splitter = TextSplitterFactory.create(
            splitter_type="recursive_character",
            chunk_size=500,
            chunk_overlap=0,
        )
        mock_vectorstore = MagicMock()
        mock_vectorstore.similarity_search.return_value = []
        mock_vectorstore.add_documents.return_value = None
        mock_blob_client = MagicMock()
        mock_blob_client.download.return_value = None
        mock_blob_client.upload.return_value = "https://test.blob.core.windows.net/ami-manifests/test"
        mock_blob_client.list_blobs.return_value = []

        with patch("base.rag_factory.VectorStoreFactory.create", return_value=mock_vectorstore):
            mgr = VerifiedContentManager(
                embedder=mock_embedder,
                text_splitter=text_splitter,
                collection_name="test_verified",
                vectorstore_type="azure_ai_search",
                azure_endpoint="https://test.search.windows.net",
                azure_key="test-key",
                blob_client=mock_blob_client,
                manifests_container="ami-manifests",
                course_content_container="ami-course-content",
            )
        return mgr

    def test_from_config_creates_manager(self):
        from base.verified_content_manager import VerifiedContentManager

        config = {
            "embedding": {"model_name": "text-embedding-3-small", "provider": "openai"},
            "rag": {"chunk_size": 500},
            "vectorstore": {"type": "azure_ai_search", "collection_name": "ami-web-results"},
            "verified_content": {"collection_name": "test_vc"},
            "azure_search": {
                "endpoint": "https://test.search.windows.net",
                "key": "test-key",
                "verified_index_name": "test_vc",
            },
            "blob_storage": {
                "connection_string": "",
                "manifests_container": "ami-manifests",
                "course_content_container": "ami-course-content",
            },
        }
        mock_embedder = MagicMock()
        mock_vectorstore = MagicMock()
        mock_blob_client = MagicMock()
        with patch("base.embedder_factory.EmbedderFactory.create", return_value=mock_embedder), \
             patch("base.rag_factory.VectorStoreFactory.create", return_value=mock_vectorstore), \
             patch("base.blob_storage.BlobStorageClient", return_value=mock_blob_client):
            mgr = VerifiedContentManager.from_config(config)
        assert mgr is not None
        assert mgr.collection_name == "test_vc"
        assert mgr.course_content_container == "ami-course-content"

    def test_compute_snapshot_hash_deterministic(self, manager):
        """Same blob list always produces the same hash."""
        blobs = [
            _make_blob("TEST_course_2024/Lectures/Lec_1.pdf"),
            _make_blob("TEST_course_2024/Syllabus/data.json"),
        ]
        h1 = manager._compute_snapshot_hash(blobs)
        h2 = manager._compute_snapshot_hash(blobs)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_snapshot_hash_order_independent(self, manager):
        """Hash is the same regardless of blob list order (sorted by name internally)."""
        blobs_a = [
            _make_blob("TEST/Lectures/Lec_1.pdf"),
            _make_blob("TEST/Syllabus/data.json"),
        ]
        blobs_b = [
            _make_blob("TEST/Syllabus/data.json"),
            _make_blob("TEST/Lectures/Lec_1.pdf"),
        ]
        assert manager._compute_snapshot_hash(blobs_a) == manager._compute_snapshot_hash(blobs_b)

    def test_compute_snapshot_hash_differs_on_change(self, manager):
        """Different blob lists produce different hashes."""
        blobs_v1 = [_make_blob("TEST/Lectures/Lec_1.pdf", etag='"0xAAA"', size=1000)]
        blobs_v2 = [_make_blob("TEST/Lectures/Lec_1.pdf", etag='"0xBBB"', size=2000)]
        assert manager._compute_snapshot_hash(blobs_v1) != manager._compute_snapshot_hash(blobs_v2)

    def test_index_verified_content_from_blobs(self, manager):
        """index_verified_content processes JSON/text blobs and calls vectorstore.add_documents."""
        json_blob = _make_blob("TEST_course_2024/Syllabus/data.json")
        py_blob = _make_blob("TEST_course_2024/References/code.py")

        json_bytes = json.dumps({"title": "Test", "content": "Python fundamentals here."}).encode()
        py_bytes = b"def hello():\n    print('Hello World')\n"

        def _fake_download(container, blob_name):
            if blob_name.endswith(".json"):
                return json_bytes
            return py_bytes

        manager.blob_client.download.side_effect = _fake_download

        with patch.object(manager, "_get_document_count", return_value=2):
            count = manager.index_verified_content([json_blob, py_blob])

        assert manager.vectorstore.add_documents.called
        assert count >= 0

    def test_index_verified_content_pdf_uses_url_path(self, manager):
        """PDF/PPTX path should pass SAS URL via url_path to Azure DI loader."""
        pdf_blob = _make_blob("TEST_course_2024/Lectures/Lec_1.pdf")
        sas_url = "https://test.blob.core.windows.net/ami-course-content/Lec_1.pdf?sas"
        manager.blob_client.generate_sas_url.return_value = sas_url
        fake_docs = [
            Document(
                page_content=(
                    "This lecture page has enough content to pass low signal filtering and get indexed."
                ),
                metadata={"page_number": 1, "source": "Lec_1.pdf"},
            )
        ]

        with patch("base.verified_content_manager._load_with_azure_di", return_value=fake_docs) as mock_loader:
            count = manager.index_verified_content([pdf_blob])

        manager.blob_client.generate_sas_url.assert_called_once_with(
            manager.course_content_container, pdf_blob.name
        )
        mock_loader.assert_called_once_with(url_path=sas_url)
        assert manager.vectorstore.add_documents.called
        assert count >= 1

    def test_index_verified_content_skips_short_path_blobs(self, manager):
        """Blobs without at least 3 path segments are skipped."""
        bad_blob = _make_blob("orphan_file.pdf")  # Only 1 segment — no course/category

        with patch.object(manager, "_get_document_count", return_value=0):
            count = manager.index_verified_content([bad_blob])

        assert count == 0
        manager.vectorstore.add_documents.assert_not_called()

    def test_index_verified_content_skips_unknown_category(self, manager):
        """Blobs under an unrecognised category folder are skipped."""
        bad_blob = _make_blob("TEST_course_2024/RandomFolder/file.py")

        with patch.object(manager, "_get_document_count", return_value=0):
            count = manager.index_verified_content([bad_blob])

        assert count == 0

    def test_retrieve_empty_collection(self, manager):
        with patch.object(manager, "_get_document_count", return_value=0):
            results = manager.retrieve("anything")
        assert results == []

    def test_retrieve_filtered_passes_server_side_filters(self, manager):
        manager.vectorstore.similarity_search.return_value = [
            Document(
                page_content="Lecture page content with relevant details.",
                metadata={
                    "course_code": "6.0001",
                    "content_category": "Lectures",
                    "lecture_number": 1,
                    "page_number": 2,
                    "file_name": "Lec_1.pdf",
                },
            )
        ]
        with patch.object(manager, "_get_document_count", return_value=10):
            results = manager.retrieve_filtered(
                query="lecture content",
                k=1,
                course_code="6.0001",
                content_category="lectures",
                lecture_number=1,
                page_number=2,
                require_lecture=True,
            )

        assert len(results) == 1
        kwargs = manager.vectorstore.similarity_search.call_args.kwargs
        filters = kwargs["filters"]
        assert "course_code eq '6.0001'" in filters
        assert "content_category eq 'Lectures'" in filters
        assert "lecture_number eq 1" in filters
        assert "page_number eq 2" in filters
        assert "(lecture_number ne null or content_category eq 'Lectures')" in filters

    def test_retrieve_filtered_falls_back_when_server_filter_fields_missing(self, manager):
        doc = Document(
            page_content="Syllabus section with enough matching text.",
            metadata={
                "course_code": "6.0001",
                "content_category": "Syllabus",
                "file_name": "syllabus.json",
            },
        )
        manager.vectorstore.similarity_search.side_effect = [
            Exception("Invalid expression: Could not find a property named 'course_code'"),
            [doc],
        ]

        with patch.object(manager, "_get_document_count", return_value=20):
            results = manager.retrieve_filtered(
                query="syllabus",
                k=1,
                course_code="6.0001",
                content_category="Syllabus",
            )

        assert len(results) == 1
        assert manager.vectorstore.similarity_search.call_count == 2
        first_call = manager.vectorstore.similarity_search.call_args_list[0]
        second_call = manager.vectorstore.similarity_search.call_args_list[1]
        assert "filters" in first_call.kwargs
        assert "filters" not in second_call.kwargs

    def test_list_courses(self, manager, tmp_path):
        content_dir = tmp_path / "courses"
        _make_course_dir(str(content_dir), "CS101", "intro", "fall-2024")
        _make_course_dir(str(content_dir), "CS201", "advanced", "spring-2025")

        courses = manager.list_courses(str(content_dir))
        assert len(courses) == 2
        codes = {c["course_code"] for c in courses}
        assert codes == {"CS101", "CS201"}

    def test_sync_skips_when_hash_unchanged(self, manager):
        """sync_verified_content skips re-indexing when snapshot hash matches."""
        fake_blobs = [_make_blob("TEST_course_2024/Lectures/Lec_1.pdf")]
        computed_hash = manager._compute_snapshot_hash(fake_blobs)

        with patch.object(manager, "_list_source_blobs", return_value=fake_blobs), \
             patch.object(manager, "_get_stored_hash", return_value=computed_hash), \
             patch.object(manager, "_get_document_count", return_value=7), \
             patch.object(manager, "index_verified_content") as mock_index, \
             patch.object(manager, "_clear_collection") as mock_clear:
            result = manager.sync_verified_content()

        assert result["reindexed"] is False
        assert result["reason"] == "unchanged"
        mock_clear.assert_not_called()
        mock_index.assert_not_called()

    def test_sync_reindexes_when_hash_changed(self, manager):
        """sync_verified_content re-indexes when stored hash differs from computed."""
        fake_blobs = [_make_blob("TEST_course_2024/Lectures/Lec_1.pdf")]

        with patch.object(manager, "_list_source_blobs", return_value=fake_blobs), \
             patch.object(manager, "_get_stored_hash", return_value="old_hash_value"), \
             patch.object(manager, "_store_hash"), \
             patch.object(manager, "_get_document_count", return_value=7), \
             patch.object(manager, "_clear_collection") as mock_clear, \
             patch.object(manager, "index_verified_content", return_value=11) as mock_index:
            result = manager.sync_verified_content()

        assert result["reindexed"] is True
        assert result["reason"] == "hash_changed"
        mock_clear.assert_called_once()
        mock_index.assert_called_once_with(fake_blobs)

    def test_sync_reindexes_when_hash_missing(self, manager):
        """sync_verified_content re-indexes when no stored hash exists."""
        fake_blobs = [_make_blob("TEST_course_2024/Syllabus/syllabus.json")]

        with patch.object(manager, "_list_source_blobs", return_value=fake_blobs), \
             patch.object(manager, "_get_stored_hash", return_value=None), \
             patch.object(manager, "_store_hash"), \
             patch.object(manager, "_get_document_count", return_value=5), \
             patch.object(manager, "_clear_collection") as mock_clear, \
             patch.object(manager, "index_verified_content", return_value=9) as mock_index:
            result = manager.sync_verified_content()

        assert result["reindexed"] is True
        assert result["reason"] == "missing_hash"
        mock_clear.assert_called_once()
        mock_index.assert_called_once_with(fake_blobs)

    def test_sync_reindexes_when_empty_collection(self, manager):
        """sync_verified_content re-indexes when collection is empty regardless of hash."""
        fake_blobs = [_make_blob("TEST_course_2024/Lectures/Lec_2.pdf")]
        computed_hash = manager._compute_snapshot_hash(fake_blobs)

        with patch.object(manager, "_list_source_blobs", return_value=fake_blobs), \
             patch.object(manager, "_get_stored_hash", return_value=computed_hash), \
             patch.object(manager, "_store_hash"), \
             patch.object(manager, "_get_document_count", return_value=0), \
             patch.object(manager, "_clear_collection") as mock_clear, \
             patch.object(manager, "index_verified_content", return_value=5) as mock_index:
            result = manager.sync_verified_content()

        assert result["reindexed"] is True
        assert result["reason"] == "empty_collection"
        mock_clear.assert_not_called()  # Nothing to clear
        mock_index.assert_called_once()


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
