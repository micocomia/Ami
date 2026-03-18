from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    """Configuration for the LLM provider. See LangChain documentation for details."""
    provider: str = "openai"  # e.g., openai, azure-openai, ollama, anthropic, groq
    model_name: str = "gpt-4o"
    base_url: Optional[str] = None


@dataclass
class EmbeddingConfig:
    provider: str = "openai"
    model_name: str = "text-embedding-3-small"


@dataclass
class SearchConfig:
    provider: str = "duckduckgo"  # tavily, serper, bing, duckduckgo, brave, searx, you
    max_results: int = 5


@dataclass
class BlobStorageConfig:
    connection_string: str = ""
    manifests_container: str = "ami-manifests"
    audio_container: str = "ami-audio"
    diagrams_container: str = "ami-diagrams"
    course_content_container: str = "ami-course-content"


@dataclass
class CosmosConfig:
    connection_string: str = ""
    database_name: str = "ami-userdata"


@dataclass
class VectorstoreConfig:
    type: str = "azure_ai_search"
    collection_name: str = "ami-web-results"

@dataclass
class RAGConfig:
    chunk_size: int = 1000
    num_retrieval_results: int = 5
    allow_parallel: bool = True
    max_workers: int = 3


@dataclass
class AppConfig:
    environment: str = "dev"  # dev | staging | prod
    debug: bool = True
    log_level: str = "INFO"

    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    vectorstore: VectorstoreConfig = field(default_factory=VectorstoreConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    blob_storage: BlobStorageConfig = field(default_factory=BlobStorageConfig)
    cosmos: CosmosConfig = field(default_factory=CosmosConfig)
