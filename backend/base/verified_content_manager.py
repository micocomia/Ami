import hashlib
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Union

from omegaconf import DictConfig
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters.base import TextSplitter

from base.embedder_factory import EmbedderFactory
from base.rag_factory import TextSplitterFactory, VectorStoreFactory
from base.verified_content_loader import (
    SKIP_FILES,
    SUPPORTED_EXTENSIONS,
    CONTENT_CATEGORIES,
    _extract_lecture_number,
    _effective_content_category,
    _load_blob_text,
    _load_blob_json,
    _load_with_azure_di,
    scan_courses,
)
from utils.config import ensure_config_dict

logger = logging.getLogger(__name__)

_SNAPSHOT_BLOB_NAME = "verified-content-snapshot.hash"


class VerifiedContentManager:

    def __init__(
        self,
        embedder: Embeddings,
        text_splitter: TextSplitter,
        collection_name: str = "verified_content",
        vectorstore_type: str = "azure_ai_search",
        azure_endpoint: Optional[str] = None,
        azure_key: Optional[str] = None,
        blob_client=None,
        manifests_container: str = "ami-manifests",
        course_content_container: str = "ami-course-content",
    ):
        self.embedder = embedder
        self.text_splitter = text_splitter
        self.collection_name = collection_name
        self.azure_endpoint = azure_endpoint or os.environ.get("AZURE_SEARCH_ENDPOINT", "")
        self.azure_key = azure_key or os.environ.get("AZURE_SEARCH_KEY", "")
        self.blob_client = blob_client
        self.manifests_container = manifests_container
        self.course_content_container = course_content_container
        self.vectorstore: VectorStore = VectorStoreFactory.create(
            vectorstore_type=vectorstore_type,
            collection_name=collection_name,
            persist_directory=".",
            embedder=embedder,
            azure_endpoint=self.azure_endpoint,
            azure_key=self.azure_key,
        )

    @staticmethod
    def from_config(
        config: Union[DictConfig, Dict[str, Any]],
    ) -> "VerifiedContentManager":
        from base.blob_storage import BlobStorageClient
        config = ensure_config_dict(config)
        embedder = EmbedderFactory.create(
            model=config.get("embedding", {}).get("model_name", "text-embedding-3-small"),
            model_provider=config.get("embedding", {}).get("provider", "openai"),
        )
        verified_cfg = config.get("verified_content", {})
        text_splitter = TextSplitterFactory.create(
            splitter_type=config.get("rag", {}).get("text_splitter_type", "recursive_character"),
            chunk_size=verified_cfg.get("chunk_size", 500),
            chunk_overlap=config.get("rag", {}).get("chunk_overlap", 0),
        )
        azure_cfg = config.get("azure_search", {})
        index_name = azure_cfg.get("verified_index_name",
                     verified_cfg.get("collection_name", "ami-verified-content"))
        blob_cfg = config.get("blob_storage", {})
        conn_str = blob_cfg.get("connection_string") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        blob_client = BlobStorageClient(conn_str) if conn_str else None
        return VerifiedContentManager(
            embedder=embedder,
            text_splitter=text_splitter,
            collection_name=index_name,
            vectorstore_type="azure_ai_search",
            azure_endpoint=azure_cfg.get("endpoint") or os.environ.get("AZURE_SEARCH_ENDPOINT"),
            azure_key=azure_cfg.get("key") or os.environ.get("AZURE_SEARCH_KEY"),
            blob_client=blob_client,
            manifests_container=blob_cfg.get("manifests_container", "ami-manifests"),
            course_content_container=blob_cfg.get("course_content_container", "ami-course-content"),
        )

    # ── Snapshot-hash helpers ──────────────────────────────────────────────

    @staticmethod
    def _compute_snapshot_hash(blobs) -> str:
        """Deterministic SHA256 hash from blob metadata. Does not read file content."""
        sorted_blobs = sorted(blobs, key=lambda b: b.name)
        entries = [
            [
                b.name,
                str(b.etag).strip('"'),  # Azure ETags include surrounding double-quotes
                b.size,
                b.last_modified.isoformat() if b.last_modified else "",
            ]
            for b in sorted_blobs
        ]
        payload = json.dumps(entries, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _get_stored_hash(self) -> Optional[str]:
        """Download stored snapshot hash from blob storage. Returns None if absent."""
        if not self.blob_client:
            return None
        data = self.blob_client.download(self.manifests_container, _SNAPSHOT_BLOB_NAME)
        if data is None:
            return None
        try:
            return data.decode("utf-8").strip()
        except Exception as e:
            logger.warning(f"Failed to decode stored snapshot hash: {e}")
            return None

    def _store_hash(self, h: str) -> None:
        """Upload snapshot hash to blob storage."""
        if not self.blob_client:
            logger.warning("No blob client configured — snapshot hash not saved")
            return
        self.blob_client.upload(
            self.manifests_container,
            _SNAPSHOT_BLOB_NAME,
            h.encode("utf-8"),
            content_type="text/plain",
        )
        logger.info(f"Saved snapshot hash to '{self.manifests_container}/{_SNAPSHOT_BLOB_NAME}'")

    def _list_source_blobs(self) -> list:
        """List blobs in the course-content container, filtered to supported extensions."""
        if not self.blob_client:
            logger.warning("No blob client configured — cannot list source blobs")
            return []
        blobs = self.blob_client.list_blobs(self.course_content_container)
        filtered = []
        for b in blobs:
            fname = b.name.split("/")[-1] if "/" in b.name else b.name
            if fname in SKIP_FILES or fname.startswith("."):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            filtered.append(b)
        logger.info(f"Found {len(filtered)} supported blobs in '{self.course_content_container}'")
        return filtered

    # ── Azure Search helpers ───────────────────────────────────────────────

    def _get_azure_search_client(self):
        from azure.search.documents import SearchClient
        from azure.core.credentials import AzureKeyCredential
        return SearchClient(
            endpoint=self.azure_endpoint,
            index_name=self.collection_name,
            credential=AzureKeyCredential(self.azure_key),
        )

    def _get_document_count(self) -> int:
        try:
            return self._get_azure_search_client().get_document_count()
        except Exception as e:
            logger.warning(f"Could not get document count from Azure Search: {e}")
            return -1  # unknown → sync falls through to hash check

    def _clear_collection(self) -> None:
        client = self._get_azure_search_client()
        results = list(client.search("*", select=["id"]))
        if results:
            for i in range(0, len(results), 1000):
                client.delete_documents(documents=[{"id": r["id"]} for r in results[i:i+1000]])
            logger.info(f"Cleared {len(results)} docs from '{self.collection_name}'")
        else:
            logger.info(f"Index '{self.collection_name}' was already empty")

    # ── Sync ──────────────────────────────────────────────────────────────

    def sync_verified_content(self, *, force: bool = False) -> Dict[str, Any]:
        """Sync verified-content index to blob storage.

        Lists blobs in the course-content container, computes a snapshot hash
        from their metadata, and re-indexes only when the hash has changed or
        the collection is empty.  No local files are required.
        """
        blobs = self._list_source_blobs()
        computed_hash = self._compute_snapshot_hash(blobs)
        stored_hash = self._get_stored_hash()
        existing_count = self._get_document_count()

        reason = "unchanged"
        should_reindex = force
        if force:
            reason = "force"
        elif existing_count == 0:
            should_reindex = True
            reason = "empty_collection"
        elif existing_count < 0:
            # Count unknown (Azure unavailable) — rely on hash
            if stored_hash is None:
                should_reindex = True
                reason = "missing_hash"
            elif stored_hash != computed_hash:
                should_reindex = True
                reason = "hash_changed"
        elif stored_hash is None:
            should_reindex = True
            reason = "missing_hash"
        elif stored_hash != computed_hash:
            should_reindex = True
            reason = "hash_changed"

        if not should_reindex:
            logger.info(
                f"Verified content unchanged for collection '{self.collection_name}' "
                f"({len(blobs)} blob(s)); skipping re-index."
            )
            return {
                "reindexed": False,
                "reason": reason,
                "collection_count": existing_count,
                "snapshot_hash": computed_hash,
            }

        if existing_count > 0:
            self._clear_collection()

        indexed_count = self.index_verified_content(blobs)
        self._store_hash(computed_hash)
        logger.info(
            f"Verified content sync completed for '{self.collection_name}' "
            f"(reason={reason}, indexed={indexed_count}, blobs={len(blobs)})."
        )
        return {
            "reindexed": True,
            "reason": reason,
            "collection_count": indexed_count,
            "snapshot_hash": computed_hash,
        }

    def index_verified_content(self, blobs) -> int:
        """Load blobs from the course-content container, split, and add to vectorstore."""
        if not blobs:
            logger.warning("No source blobs to index.")
            return 0

        def _process_blob(blob):
            parts = blob.name.split("/")
            if len(parts) < 3:
                logger.debug(f"Skipping blob with unexpected path: {blob.name}")
                return []

            course_folder = parts[0]
            category = parts[1]
            fname = parts[-1]

            if category not in CONTENT_CATEGORIES:
                return []

            # Parse course metadata from folder: {code}_{name}_{term}
            folder_parts = course_folder.split("_", 2)
            if len(folder_parts) >= 3:
                course_code = folder_parts[0]
                course_name = folder_parts[1].replace("-", " ")
                term = folder_parts[2].replace("-", " ")
            elif len(folder_parts) == 2:
                course_code = folder_parts[0]
                course_name = folder_parts[1].replace("-", " ")
                term = "unknown"
            else:
                course_code = course_folder
                course_name = course_folder
                term = "unknown"

            ext = os.path.splitext(fname)[1].lower()
            lecture_number = _extract_lecture_number(fname)
            effective_category = _effective_content_category(category, fname)

            try:
                if ext in (".pdf", ".pptx"):
                    sas_url = self.blob_client.generate_sas_url(
                        self.course_content_container, blob.name
                    )
                    docs = _load_with_azure_di(url_source=sas_url)
                elif ext == ".json":
                    content_bytes = self.blob_client.download(
                        self.course_content_container, blob.name
                    )
                    if content_bytes is None:
                        return []
                    docs = _load_blob_json(content_bytes, blob.name)
                else:
                    # .py, .txt, .md
                    content_bytes = self.blob_client.download(
                        self.course_content_container, blob.name
                    )
                    if content_bytes is None:
                        return []
                    docs = _load_blob_text(content_bytes, blob.name)
            except Exception as e:
                logger.error(f"Failed to load blob '{blob.name}': {e}")
                return []

            for doc in docs:
                doc.metadata.update({
                    "source_type": "verified_content",
                    "course_code": course_code,
                    "course_name": course_name,
                    "term": term,
                    "content_category": effective_category,
                    "file_name": fname,
                    "lecture_number": lecture_number,
                })
            return docs

        all_documents: List[Document] = []
        max_workers = min(4, max(1, len(blobs)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_blob, blob): blob for blob in blobs}
            for future in as_completed(futures):
                blob = futures[future]
                try:
                    docs = future.result()
                    all_documents.extend(docs)
                except Exception as e:
                    logger.error(f"Failed processing blob '{blob.name}': {e}")

        if not all_documents:
            logger.warning("No verified content documents found to index.")
            return 0

        all_documents = [doc for doc in all_documents if len(doc.page_content.strip()) > 0]
        split_docs = self.text_splitter.split_documents(all_documents)
        prefilter_count = len(split_docs)

        def is_low_signal_chunk(doc: Document) -> bool:
            text = (doc.page_content or "").strip().lower()
            file_name = str((doc.metadata or {}).get("file_name", "")).lower()
            if file_name.endswith(".py"):
                return False
            if not text:
                return True
            boilerplate_markers = [
                "for information about citing these materials",
                "terms of use",
                "ocw.mit.edu/terms",
                "download slides and .py files and follow along",
            ]
            if any(m in text for m in boilerplate_markers):
                return True
            if text.startswith("welcome!") or ("today" in text and "course info" in text):
                return True
            alpha_chars = sum(1 for ch in text if ch.isalpha())
            return alpha_chars < 40

        filtered_docs = [d for d in split_docs if not is_low_signal_chunk(d)]
        if filtered_docs:
            split_docs = filtered_docs
        else:
            logger.warning(
                "Low-signal filtering removed all verified chunks; "
                f"falling back to unfiltered set ({prefilter_count} chunk(s))."
            )

        for doc in split_docs:
            if "source_type" not in doc.metadata:
                doc.metadata["source_type"] = "verified_content"
            # Azure AI Search requires flat primitive metadata values
            doc.metadata = {
                k: v for k, v in doc.metadata.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }

        if not split_docs:
            logger.warning("No verified content chunks available to index after preprocessing.")
            return 0

        self.vectorstore.add_documents(split_docs)
        final_count = self._get_document_count()
        logger.info(
            f"Indexed {len(split_docs)} verified content chunks into "
            f"'{self.collection_name}' (total: {final_count})"
        )
        return final_count

    # ── Retrieval ─────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        """Similarity search against the verified content collection."""
        try:
            count = self._get_document_count()
            if count == 0:
                return []
            results = self.vectorstore.similarity_search(query, k=k)
            return results
        except Exception as e:
            logger.error(f"Error retrieving from verified content: {e}")
            return []

    def retrieve_filtered(
        self,
        query: str,
        k: int = 5,
        *,
        course_code: Optional[str] = None,
        content_category: Optional[str] = None,
        lecture_number: Optional[int] = None,
        page_number: Optional[int] = None,
        exclude_file_names: Optional[List[str]] = None,
        require_lecture: bool = False,
    ) -> List[Document]:
        """Similarity search with optional metadata constraints and lightweight reranking."""
        try:
            count = self._get_document_count()
            if count == 0:
                return []
            fetch_k = max(k * 8, 40)
            candidates = self.vectorstore.similarity_search(query, k=fetch_k)
        except Exception as e:
            logger.error(f"Error retrieving filtered verified content: {e}")
            return []

        excluded = {x.lower() for x in (exclude_file_names or [])}

        def is_lecture_doc(meta: Dict[str, Any]) -> bool:
            if meta.get("lecture_number") is not None:
                return True
            category = str(meta.get("content_category", "")).lower().strip()
            if category == "lectures":
                return True
            file_name = str(meta.get("file_name", "")).lower().strip()
            return file_name.startswith("lec_") and file_name.endswith(".pdf")

        filtered: List[Document] = []
        for d in candidates:
            meta = d.metadata or {}
            code = str(meta.get("course_code", "")).strip().lower()
            cat = str(meta.get("content_category", "")).strip().lower()
            fname = str(meta.get("file_name", "")).strip().lower()

            if course_code and code and code != course_code.lower():
                continue
            if content_category and cat != content_category.lower():
                continue
            if lecture_number is not None and meta.get("lecture_number") != lecture_number:
                continue
            if page_number is not None and meta.get("page_number") != page_number:
                continue
            if fname in excluded:
                continue
            if require_lecture and not is_lecture_doc(meta):
                continue
            filtered.append(d)

        if not filtered:
            return []

        query_tokens = {
            t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", query.lower())
            if len(t) > 1
        }

        def score(doc: Document) -> tuple:
            meta = doc.metadata or {}
            meta_text = " ".join([
                str(meta.get("title", "")),
                str(meta.get("course_code", "")),
                str(meta.get("course_name", "")),
                str(meta.get("file_name", "")),
                str(meta.get("content_category", "")),
            ]).lower()
            doc_tokens = {
                t for t in re.findall(r"[a-z0-9][a-z0-9\.\-_]+", f"{meta_text} {doc.page_content.lower()}")
                if len(t) > 1
            }
            overlap = len(query_tokens & doc_tokens)
            lecture_boost = 3 if is_lecture_doc(meta) else 0
            syllabus_penalty = -2 if "syllabus" in str(meta.get("file_name", "")).lower() else 0
            return (overlap + lecture_boost + syllabus_penalty, overlap)

        ranked = sorted(filtered, key=score, reverse=True)
        return ranked[:k]

    def list_courses(self, base_dir: str = "resources/verified-course-content") -> List[Dict[str, Any]]:
        """Return list of course metadata dicts from the verified content directory."""
        return scan_courses(base_dir)
