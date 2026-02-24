import hashlib
import json
import logging
import os
import re
import stat
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
    load_all_verified_content,
    scan_courses,
)
from utils.config import ensure_config_dict

logger = logging.getLogger(__name__)


class VerifiedContentManager:
    MANIFEST_VERSION = 1

    def __init__(
        self,
        embedder: Embeddings,
        text_splitter: TextSplitter,
        persist_directory: str = "./data/vectorstore",
        collection_name: str = "verified_content",
    ):
        self.embedder = embedder
        self.text_splitter = text_splitter
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.vectorstore: VectorStore = VectorStoreFactory.create(
            vectorstore_type="chroma",
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedder=embedder,
        )

    @staticmethod
    def from_config(
        config: Union[DictConfig, Dict[str, Any]],
    ) -> "VerifiedContentManager":
        config = ensure_config_dict(config)
        embedder = EmbedderFactory.create(
            model=config.get("embedder", {}).get("model_name", "sentence-transformers/all-mpnet-base-v2"),
            model_provider=config.get("embedder", {}).get("provider", "huggingface"),
        )
        verified_cfg = config.get("verified_content", {})
        text_splitter = TextSplitterFactory.create(
            splitter_type=config.get("rag", {}).get("text_splitter_type", "recursive_character"),
            chunk_size=verified_cfg.get("chunk_size", 500),
            chunk_overlap=config.get("rag", {}).get("chunk_overlap", 0),
        )
        return VerifiedContentManager(
            embedder=embedder,
            text_splitter=text_splitter,
            persist_directory=config.get("vectorstore", {}).get("persist_directory", "./data/vectorstore"),
            collection_name=verified_cfg.get("collection_name", "verified_content"),
        )

    def _manifest_path(self) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", self.collection_name)
        return os.path.join(self.persist_directory, f"{safe_name}_manifest.json")

    @staticmethod
    def _hash_file(file_path: str) -> str:
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _iter_supported_files(base_dir: str) -> List[str]:
        if not os.path.isdir(base_dir):
            return []
        paths: List[str] = []
        for root, _dirs, files in os.walk(base_dir):
            for fname in files:
                if fname in SKIP_FILES or fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                paths.append(os.path.join(root, fname))
        return sorted(paths)

    def _build_manifest(self, base_dir: str) -> Dict[str, Any]:
        files: List[Dict[str, Any]] = []
        base_dir_abs = os.path.abspath(base_dir)
        for file_path in self._iter_supported_files(base_dir_abs):
            try:
                file_stat = os.stat(file_path, follow_symlinks=False)
            except OSError as e:
                logger.warning(f"Skipping unreadable verified content file '{file_path}': {e}")
                continue

            if not stat.S_ISREG(file_stat.st_mode):
                logger.warning(f"Skipping non-regular verified content file '{file_path}'")
                continue

            try:
                file_hash = self._hash_file(file_path)
            except OSError as e:
                logger.warning(f"Skipping unreadable verified content file '{file_path}': {e}")
                continue

            rel_path = os.path.relpath(file_path, base_dir_abs).replace(os.sep, "/")
            files.append(
                {
                    "path": rel_path,
                    "size": file_stat.st_size,
                    "mtime_ns": file_stat.st_mtime_ns,
                    "sha256": file_hash,
                }
            )

        hash_input = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        manifest_hash = hashlib.sha256(hash_input).hexdigest()
        return {
            "version": self.MANIFEST_VERSION,
            "collection_name": self.collection_name,
            "base_dir": base_dir_abs,
            "file_count": len(files),
            "manifest_hash": manifest_hash,
            "files": files,
        }

    def _load_manifest(self) -> Optional[Dict[str, Any]]:
        manifest_path = self._manifest_path()
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return data
        except Exception as e:
            logger.warning(f"Failed to load verified content manifest '{manifest_path}': {e}")
            return None

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        os.makedirs(self.persist_directory, exist_ok=True)
        manifest_path = self._manifest_path()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    def _clear_collection(self) -> None:
        # Preferred path: drop and recreate collection handle.
        if hasattr(self.vectorstore, "delete_collection"):
            try:
                self.vectorstore.delete_collection()
                self.vectorstore = VectorStoreFactory.create(
                    vectorstore_type="chroma",
                    collection_name=self.collection_name,
                    persist_directory=self.persist_directory,
                    embedder=self.embedder,
                )
                return
            except Exception as e:
                logger.warning(f"delete_collection() failed for '{self.collection_name}': {e}")

        # Fallback: delete all entries in-place.
        try:
            if hasattr(self.vectorstore, "_collection"):
                self.vectorstore._collection.delete(where={})
                return
        except Exception as e:
            logger.warning(f"_collection.delete(where={{}}) failed for '{self.collection_name}': {e}")

        # Last-resort fallback: enumerate IDs and delete.
        try:
            ids: List[str] = []
            if hasattr(self.vectorstore, "get"):
                payload = self.vectorstore.get(include=[])
                if isinstance(payload, dict):
                    ids = payload.get("ids", []) or []
            if ids and hasattr(self.vectorstore, "delete"):
                self.vectorstore.delete(ids=ids)
        except Exception as e:
            raise RuntimeError(f"Unable to clear collection '{self.collection_name}': {e}") from e

    def sync_verified_content(self, base_dir: str, *, force: bool = False) -> Dict[str, Any]:
        """Sync verified-content index to disk resources.

        Reindexes the verified collection when files are added, deleted, or updated.
        """
        current_manifest = self._build_manifest(base_dir)
        stored_manifest = self._load_manifest()
        existing_count = self.vectorstore._collection.count()

        reason = "unchanged"
        should_reindex = force
        if force:
            reason = "force"
        elif existing_count == 0:
            should_reindex = True
            reason = "empty_collection"
        elif stored_manifest is None:
            should_reindex = True
            reason = "missing_manifest"
        elif stored_manifest.get("manifest_hash") != current_manifest.get("manifest_hash"):
            should_reindex = True
            reason = "manifest_changed"

        if not should_reindex:
            logger.info(
                f"Verified content unchanged for collection '{self.collection_name}' "
                f"({current_manifest.get('file_count', 0)} file(s)); skipping re-index."
            )
            return {
                "reindexed": False,
                "reason": reason,
                "collection_count": existing_count,
                "manifest_hash": current_manifest.get("manifest_hash"),
            }

        if existing_count > 0:
            self._clear_collection()

        indexed_count = self.index_verified_content(base_dir)
        self._save_manifest(current_manifest)
        logger.info(
            f"Verified content sync completed for '{self.collection_name}' "
            f"(reason={reason}, indexed={indexed_count}, files={current_manifest.get('file_count', 0)})."
        )
        return {
            "reindexed": True,
            "reason": reason,
            "collection_count": indexed_count,
            "manifest_hash": current_manifest.get("manifest_hash"),
        }

    def index_verified_content(self, base_dir: str) -> int:
        """Loads, splits, and adds verified content to vectorstore. Skips if collection already has documents."""
        existing_count = self.vectorstore._collection.count()
        if existing_count > 0:
            logger.info(
                f"Verified content collection '{self.collection_name}' already has "
                f"{existing_count} documents. Skipping indexing."
            )
            return existing_count

        documents = load_all_verified_content(base_dir)
        if not documents:
            logger.warning("No verified content documents found to index.")
            return 0

        documents = [doc for doc in documents if len(doc.page_content.strip()) > 0]
        split_docs = self.text_splitter.split_documents(documents)
        prefilter_count = len(split_docs)

        def is_low_signal_chunk(doc: Document) -> bool:
            text = (doc.page_content or "").strip().lower()
            file_name = str((doc.metadata or {}).get("file_name", "")).lower()
            # Keep code files available for reference retrieval.
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
            # Filter generic title/agenda pages that add little topical signal.
            if text.startswith("welcome!") or ("today" in text and "course info" in text):
                return True
            alpha_chars = sum(1 for ch in text if ch.isalpha())
            return alpha_chars < 40

        filtered_docs = [d for d in split_docs if not is_low_signal_chunk(d)]
        if filtered_docs:
            split_docs = filtered_docs
        else:
            # Never index an empty list due to over-aggressive filtering;
            # keep original chunks as a safe fallback.
            logger.warning(
                "Low-signal filtering removed all verified chunks; "
                f"falling back to unfiltered set ({prefilter_count} chunk(s))."
            )

        for doc in split_docs:
            if "source_type" not in doc.metadata:
                doc.metadata["source_type"] = "verified_content"
            # ChromaDB only accepts str, int, float, bool, or None metadata values.
            # Docling injects complex nested dicts/lists — strip them out.
            doc.metadata = {
                k: v for k, v in doc.metadata.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }

        if not split_docs:
            logger.warning("No verified content chunks available to index after preprocessing.")
            return 0

        self.vectorstore.add_documents(split_docs, embedding_function=self.embedder)
        final_count = self.vectorstore._collection.count()
        logger.info(
            f"Indexed {len(split_docs)} verified content chunks into "
            f"'{self.collection_name}' (total: {final_count})"
        )
        return final_count

    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        """Similarity search against the verified content collection."""
        try:
            count = self.vectorstore._collection.count()
            if count == 0:
                return []
            results = self.vectorstore.similarity_search(query, k=min(k, count))
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
            count = self.vectorstore._collection.count()
            if count == 0:
                return []
            fetch_k = min(count, max(k * 8, 40))
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

        def score(doc: Document) -> tuple[int, int]:
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
