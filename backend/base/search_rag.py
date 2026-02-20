import os
import logging
from typing import List, Optional, Dict, Any, Union
from omegaconf import DictConfig

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters.base import TextSplitter

from base.dataclass import SearchResult
from base.embedder_factory import EmbedderFactory
from base.searcher_factory import SearcherFactory, SearchRunner
from base.rag_factory import TextSplitterFactory, VectorStoreFactory
from base.verified_content_manager import VerifiedContentManager
from utils.config import ensure_config_dict

logger = logging.getLogger(__name__)


class SearchRagManager:

    def __init__(
        self,
        embedder: Embeddings,
        text_splitter: Optional[TextSplitter] = None,
        vectorstore: Optional[VectorStore] = None,
        search_runner: Optional[SearchRunner] = None,
        max_retrieval_results: int = 5,
        verified_content_manager: Optional[VerifiedContentManager] = None,
    ):
        self.embedder = embedder
        self.text_splitter = text_splitter
        self.vectorstore = vectorstore
        self.search_runner = search_runner
        self.max_retrieval_results = max_retrieval_results
        self.verified_content_manager = verified_content_manager

    @staticmethod
    def from_config(
        config: Union[DictConfig, Dict[str, Any]],
    ) -> "SearchRagManager":
        config = ensure_config_dict(config)
        embedder = EmbedderFactory.create(
            model=config.get("embedder", {}).get("model_name", "sentence-transformers/all-mpnet-base-v2"),
            model_provider=config.get("embedder", {}).get("provider", "huggingface"),
        )

        text_splitter = TextSplitterFactory.create(
            splitter_type=config.get("rag", {}).get("text_splitter_type", "recursive_character"),
            chunk_size=config.get("rag", {}).get("chunk_size", 1000),
            chunk_overlap=config.get("rag", {}).get("chunk_overlap", 0),
        )

        vectorstore = VectorStoreFactory.create(
            vectorstore_type=config.get("vectorstore", {}).get("type", "chroma"),
            collection_name=config.get("vectorstore", {}).get("collection_name", "default_collection"),
            persist_directory=config.get("vectorstore", {}).get("persist_directory", "./data/vectorstore"),
            embedder=embedder,
        )

        search_runner = SearchRunner.from_config(
            config=config
        )

        verified_content_manager = None
        verified_cfg = config.get("verified_content", {})
        if verified_cfg.get("enabled", False):
            try:
                verified_content_manager = VerifiedContentManager.from_config(config)
                logger.info("VerifiedContentManager initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize VerifiedContentManager: {e}")

        return SearchRagManager(
            embedder=embedder,
            text_splitter=text_splitter,
            vectorstore=vectorstore,
            search_runner=search_runner,
            max_retrieval_results=config.get("rag", {}).get("num_retrieval_results", 5),
            verified_content_manager=verified_content_manager,
        )


    def search(self, query: str) -> List[SearchResult]:
        if not self.search_runner:
            raise ValueError("SearcherRunner is not initialized.")
        results = self.search_runner.invoke(query)
        return results

    def add_documents(
        self,
        documents: List[Document],
        source_type: Optional[str] = None
    ) -> None:
        if len(documents) == 0:
            logger.warning("No documents to add to the vectorstore.")
            return
        if not self.vectorstore:
            raise ValueError("VectorStore is not initialized.")
        documents = [doc for doc in documents if len(doc.page_content.strip()) > 0]
        # Add source_type metadata if provided
        if source_type:
            for doc in documents:
                doc.metadata["source_type"] = source_type
        if self.text_splitter:
            split_docs = self.text_splitter.split_documents(documents)
        else:
            split_docs = documents
        self.vectorstore.add_documents(split_docs, embedding_function=self.embedder)
        logger.info(f"Added {len(split_docs)} documents to the vectorstore.")

    def retrieve(self, query: str, k: Optional[int] = None) -> List[Document]:
        k = k or self.max_retrieval_results
        if not self.vectorstore:
            raise ValueError("VectorStore is not initialized.")
        retrieval = self.vectorstore.similarity_search(query, k=k)
        return retrieval

    def invoke(self, query: str) -> List[Document]:
        results = self.search(query)
        documents = [res.document for res in results if res.document is not None]
        # Preserve original web search metadata (title, source_type, source/URL)
        # before the vectorstore round-trip which may lose it during splitting.
        original_meta = {}
        for res in results:
            if res.document is not None:
                original_meta[res.link] = {
                    "title": res.title,
                    "source_type": "web_search",
                    "source": res.link,
                }
        self.add_documents(documents=documents)
        retrieved_docs = self.retrieve(query)
        # Re-apply web search metadata to retrieved docs
        for doc in retrieved_docs:
            src = doc.metadata.get("source", "")
            if src in original_meta:
                for key, val in original_meta[src].items():
                    if key not in doc.metadata or not doc.metadata[key]:
                        doc.metadata[key] = val
        return retrieved_docs

    def invoke_hybrid(self, query: str, k: Optional[int] = None) -> List[Document]:
        """Verified-first hybrid retrieval. Uses verified content as primary source,
        falls back to web search when insufficient results."""
        k = k or self.max_retrieval_results

        # Try verified content first
        verified_docs = []
        if self.verified_content_manager is not None:
            verified_docs = self.verified_content_manager.retrieve(query, k=k)
            logger.info(f"Verified content returned {len(verified_docs)} results for query: {query[:80]}")

        # If verified content provides enough results, return them
        if len(verified_docs) >= k:
            return verified_docs[:k]

        # Fall back to web search for remaining slots
        remaining = k - len(verified_docs)
        try:
            web_docs = self.invoke(query)
            # Tag web docs with source_type if not already tagged
            for doc in web_docs:
                if "source_type" not in doc.metadata:
                    doc.metadata["source_type"] = "web_search"
        except Exception as e:
            logger.warning(f"Web search failed, using verified results only: {e}")
            web_docs = []

        # Combine: verified first, then web
        combined = verified_docs + web_docs[:remaining]
        logger.info(
            f"Hybrid retrieval: {len(verified_docs)} verified + "
            f"{min(len(web_docs), remaining)} web = {len(combined)} total"
        )
        return combined

    def invoke_hybrid_filtered(
        self,
        query: str,
        k: Optional[int] = None,
        *,
        course_code: Optional[str] = None,
        content_category: Optional[str] = None,
        lecture_number: Optional[int] = None,
        exclude_file_names: Optional[List[str]] = None,
        require_lecture: bool = False,
        allow_web_fallback: bool = True,
    ) -> List[Document]:
        """Hybrid retrieval with metadata-constrained verified-content lookup."""
        k = k or self.max_retrieval_results

        verified_docs: List[Document] = []
        if self.verified_content_manager is not None:
            if hasattr(self.verified_content_manager, "retrieve_filtered"):
                verified_docs = self.verified_content_manager.retrieve_filtered(
                    query,
                    k=k,
                    course_code=course_code,
                    content_category=content_category,
                    lecture_number=lecture_number,
                    exclude_file_names=exclude_file_names,
                    require_lecture=require_lecture,
                )
            else:
                verified_docs = self.verified_content_manager.retrieve(query, k=k)
            logger.info(f"Filtered verified retrieval returned {len(verified_docs)} results for query: {query[:80]}")

        if len(verified_docs) >= k or not allow_web_fallback:
            return verified_docs[:k]

        remaining = k - len(verified_docs)
        try:
            web_docs = self.invoke(query)
            for doc in web_docs:
                if "source_type" not in doc.metadata:
                    doc.metadata["source_type"] = "web_search"
        except Exception as e:
            logger.warning(f"Web search failed during filtered hybrid retrieval: {e}")
            web_docs = []

        combined = verified_docs + web_docs[:remaining]
        logger.info(
            f"Filtered hybrid retrieval: {len(verified_docs)} verified + "
            f"{min(len(web_docs), remaining)} web = {len(combined)} total"
        )
        return combined


def format_docs(docs: List[Document]) -> str:
    formatted_chunks: List[str] = []
    for idx, doc in enumerate(docs):
        title = doc.metadata.get("title") if doc.metadata else None
        source = doc.metadata.get("source") if doc.metadata else None
        source_type = doc.metadata.get("source_type") if doc.metadata else None
        header_parts = [f"[{idx + 1}]"]
        if source_type:
            header_parts.append(f"({source_type})")
        if title:
            header_parts.append(title)
        if source:
            header_parts.append(f"Source: {source}")
        header = " | ".join(header_parts)
        body = doc.page_content.strip()
        formatted_chunks.append(f"{header}\n{body}")
    return "\n\n".join(formatted_chunks)



if __name__ == "__main__":
    # python -m base.search_rag
    embedder = EmbedderFactory.create(
        model="sentence-transformers/all-mpnet-base-v2",
        model_provider="huggingface"
    )

    searcher = SearcherFactory.create(
        provider="duckduckgo",
        max_results=5,
    )

    search_runner = SearchRunner(
        searcher=searcher,
        loader_type="web",
        max_search_results=5,
    )

    text_splitter = TextSplitterFactory.create(
        splitter_type="recursive_character",
        chunk_size=1000,
        chunk_overlap=0,
    )

    vectorstore = VectorStoreFactory.create(
        vectorstore_type="chroma",
        collection_name="example_collection",
        persist_directory="./data/vectorstore",
        embedder=embedder,
    )

    rag_manager = SearchRagManager(
        embedder=embedder,
        text_splitter=text_splitter,
        vectorstore=vectorstore,
        search_runner=search_runner,
    )

    from config import default_config
    rag_manager = SearchRagManager.from_config(default_config)

    results = rag_manager.search("LangChain community utilities")
    print(f"Retrieved {len(results)} search results.")
    documents = [res.document for res in results if res.document is not None]
    rag_manager.add_documents(documents=documents)

    retrieved_docs = rag_manager.retrieve("LangChain community utilities", k=5)
    print(f"Retrieved {len(retrieved_docs)} documents from vectorstore.")
    print(format_docs(retrieved_docs))
