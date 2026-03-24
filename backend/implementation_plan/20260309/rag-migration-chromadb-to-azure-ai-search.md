# RAG Migration: ChromaDB → Azure AI Search

**Date:** 2026-03-09
**Status:** COMPLETE

---

## Motivation

The backend was running out of memory (OOM) on Azure Container Service due to two large in-container memory consumers:

1. **ChromaDB** — in-memory vector index that grows with every indexed document
2. **HuggingFace `all-mpnet-base-v2`** — ~420MB local embedding model loaded at startup

Moving both vectorstore collections to **Azure AI Search Free tier** ($0/month, 3 indexes, 50MB limit) and switching embeddings to the **OpenAI API** (`text-embedding-3-small` via the existing `OPENAI_API_KEY`) eliminates both sources of in-container memory pressure.

**Two Azure AI Search indexes:**
- `ami-verified-content` — permanent indexed course materials
- `ami-web-results` — shared cross-user web search cache (avoids re-hitting the web for the same query)

---

## Changes Implemented

### Step 1 — `backend/requirements.txt`

**Removed** (eliminates in-memory embedding model and ChromaDB):
- `chromadb`
- `langchain-chroma`
- `langchain-huggingface`
- `sentence-transformers`
- `safetensors`
- `tokenizers`
- `transformers`
- `accelerate`

**Added** (Azure AI Search SDK):
```
azure-core>=1.32.0
azure-search-documents>=11.4.0
```

**Upgraded** `langchain-community` from `1.0.0a1` (alpha) to a stable release:
```
langchain-community>=0.3.0,<1.0.0
```
Required for the stable `AzureSearch` export at `langchain_community.vectorstores.AzureSearch`.

**Note:** `torch`/`torchvision` are intentionally kept — Docling installs PyTorch as a transitive dependency regardless. Removing explicit pins loses version control without reducing container size. PyTorch is only loaded into RAM if Docling actually processes a PDF at runtime (blocked by the manifest check).

---

### Step 2 — `backend/config/default.yaml`

**Embedding provider switched** from HuggingFace to OpenAI:
```yaml
# Before:
embedding:
  provider: huggingface
  model_name: sentence-transformers/all-mpnet-base-v2

# After:
embedding:
  provider: openai
  model_name: text-embedding-3-small
```

**Vectorstore type switched** to Azure AI Search:
```yaml
# Before:
vectorstore:
  persist_directory: data/vectorstore
  collection_name: non-verified-content

# After:
vectorstore:
  type: azure_ai_search
  persist_directory: data/vectorstore   # kept for manifest file path only
  collection_name: ami-web-results
```

**New `azure_search` config block added:**
```yaml
azure_search:
  endpoint: ""        # overridden by AZURE_SEARCH_ENDPOINT env var
  key: ""             # overridden by AZURE_SEARCH_KEY env var
  verified_index_name: ami-verified-content
```

---

### Step 3 — `backend/.env.example`

Added two new required environment variables:
```
AZURE_SEARCH_ENDPOINT=https://<your-service-name>.search.windows.net
AZURE_SEARCH_KEY=<your-admin-key>
```

These must be present in `backend/.env` for both local development and production deployment.

---

### Step 4 — `backend/base/rag_factory.py`

Extended `VectorStoreFactory.create()` with two new parameters (`azure_endpoint`, `azure_key`) and a new `azure_ai_search` branch:

```python
elif vectorstore_type in ["azure_ai_search", "azure_search"]:
    from langchain_community.vectorstores import AzureSearch
    endpoint = azure_endpoint or os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    key = azure_key or os.environ.get("AZURE_SEARCH_KEY", "")
    if not endpoint or not key:
        raise ValueError(
            "Azure AI Search requires AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY. "
            "Set them in backend/.env or as environment variables."
        )
    vectorstore = AzureSearch(
        azure_search_endpoint=endpoint,
        azure_search_key=key,
        index_name=collection_name,
        embedding_function=embedder.embed_query,
    )
```

`AzureSearch` auto-creates the index on first use. The Chroma branch is kept as a legacy fallback for local development.

---

### Step 5 — `backend/base/verified_content_manager.py`

Replaced all 7 ChromaDB-private API call sites. Key changes:

**Constructor** — accepts `vectorstore_type`, `azure_endpoint`, `azure_key`; stores credentials on `self` so all methods share them:
```python
def __init__(self, embedder, text_splitter,
             persist_directory="./data/vectorstore",
             collection_name="verified_content",
             vectorstore_type="azure_ai_search",
             azure_endpoint=None, azure_key=None):
    self.azure_endpoint = azure_endpoint or os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    self.azure_key = azure_key or os.environ.get("AZURE_SEARCH_KEY", "")
    self.vectorstore = VectorStoreFactory.create(
        vectorstore_type=vectorstore_type, ...,
        azure_endpoint=self.azure_endpoint, azure_key=self.azure_key,
    )
```

**`from_config()`** — reads `azure_search` config block; uses `verified_index_name` as the index for verified content:
```python
azure_cfg = config.get("azure_search", {})
index_name = azure_cfg.get("verified_index_name",
             verified_cfg.get("collection_name", "ami-verified-content"))
return VerifiedContentManager(
    ..., collection_name=index_name, vectorstore_type="azure_ai_search",
    azure_endpoint=azure_cfg.get("endpoint") or os.environ.get("AZURE_SEARCH_ENDPOINT"),
    azure_key=azure_cfg.get("key") or os.environ.get("AZURE_SEARCH_KEY"),
)
```

**`_get_azure_search_client()` helper** — returns an Azure SDK `SearchClient` using stored credentials:
```python
def _get_azure_search_client(self):
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    return SearchClient(
        endpoint=self.azure_endpoint,
        index_name=self.collection_name,
        credential=AzureKeyCredential(self.azure_key),
    )
```

**`_get_document_count()` helper** — replaces all `self.vectorstore._collection.count()` calls:
```python
def _get_document_count(self) -> int:
    try:
        return self._get_azure_search_client().get_document_count()
    except Exception as e:
        logger.warning(f"Could not get document count from Azure Search: {e}")
        return -1  # unknown → sync falls through to manifest check
```

**`_clear_collection()`** — replaced all three ChromaDB fallback paths with Azure SDK batch delete. LangChain's `AzureSearch` uses `id` as the key field name (`FIELDS_ID = "id"`):
```python
def _clear_collection(self) -> None:
    client = self._get_azure_search_client()
    results = list(client.search("*", select=["id"]))
    if results:
        for i in range(0, len(results), 1000):
            client.delete_documents(documents=[{"id": r["id"]} for r in results[i:i+1000]])
```

**`index_verified_content()`** — dropped `embedding_function=self.embedder` kwarg from `add_documents()`. Azure Search uses the embedder passed at construction time.

**`retrieve()` and `retrieve_filtered()`** — replaced `_collection.count()` guard with `_get_document_count()`. The `min(k, count)` cap is removed from `retrieve()` (Azure AI Search handles `k` gracefully when fewer docs exist); the `count == 0` early return is kept.

**`sync_verified_content()`** — updated to handle `existing_count == -1` (Azure temporarily unavailable) by falling back to manifest-only check.

---

### Step 6 — `backend/base/search_rag.py`

**`from_config()`** — reads `embedding` config key (was incorrectly `embedder`) for both `model_name` and `provider`:
```python
embedder = EmbedderFactory.create(
    model=config.get("embedding", {}).get("model_name", "text-embedding-3-small"),
    model_provider=config.get("embedding", {}).get("provider", "openai"),
)
```

Wired `azure_search` config block to `VectorStoreFactory`:
```python
azure_cfg = config.get("azure_search", {})
azure_endpoint = azure_cfg.get("endpoint") or os.environ.get("AZURE_SEARCH_ENDPOINT")
azure_key = azure_cfg.get("key") or os.environ.get("AZURE_SEARCH_KEY")
vectorstore = VectorStoreFactory.create(
    vectorstore_type=config.get("vectorstore", {}).get("type", "azure_ai_search"),
    collection_name=config.get("vectorstore", {}).get("collection_name", "ami-web-results"),
    ..., azure_endpoint=azure_endpoint, azure_key=azure_key,
)
```

**`add_documents()`** — dropped `embedding_function=self.embedder` kwarg from `self.vectorstore.add_documents(split_docs)`.

---

### Step 7 — `backend/main.py`

Wrapped `sync_verified_content()` in try/except in the `_load_stores()` startup event to prevent app crash if Azure AI Search is temporarily unavailable at startup:

```python
@app.on_event("startup")
def _load_stores():
    store.load()
    auth_store.load()
    if search_rag_manager.verified_content_manager:
        try:
            search_rag_manager.verified_content_manager.sync_verified_content(
                app_config.get("verified_content", {}).get("base_dir", "resources/verified-course-content")
            )
        except Exception as e:
            logger.warning(
                f"Verified content sync failed at startup: {e}. "
                "Retrieval will use whatever is currently in the index."
            )
```

The app now boots and serves requests even if the sync call fails — retrieval uses the pre-indexed content already in the Azure index.

---

### Step 8 — `backend/tests/test_verified_content.py`

**`manager` fixture** — now patches `VectorStoreFactory.create` with a `MagicMock` so tests do not require live Azure credentials:
```python
mock_vectorstore = MagicMock()
with patch("base.rag_factory.VectorStoreFactory.create", return_value=mock_vectorstore):
    mgr = VerifiedContentManager(
        ..., vectorstore_type="azure_ai_search",
        azure_endpoint="https://test.search.windows.net", azure_key="test-key",
    )
```

**`test_from_config_creates_manager`** — updated config to use `embedding.provider: openai`; mocks both `EmbedderFactory.create` and `VectorStoreFactory.create`.

**Sync tests** — replaced all `manager.vectorstore._collection.count.return_value = N` patterns with:
```python
with patch.object(manager, "_get_document_count", return_value=N): ...
```

**`test_index_and_retrieve`** and **`test_index_skips_if_already_indexed`** — updated to use `patch.object(manager, "_get_document_count", ...)` instead of relying on a real vectorstore.

**`test_retrieve_empty_collection`** — patches `_get_document_count` to return `0`.

---

### Step 9 — `backend/scripts/preindex_verified_content.py` (new file)

One-time pre-indexing script to run locally before deploying:

```bash
conda activate ami-backend && cd backend
python scripts/preindex_verified_content.py
```

The script:
1. Loads `backend/.env` (needs `OPENAI_API_KEY`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KEY`)
2. Instantiates `VerifiedContentManager.from_config(load_config())`
3. Calls `sync_verified_content(base_dir, force=True)`
4. Saves manifest to `backend/data/vectorstore/ami-verified-content_manifest.json`

On subsequent container restarts, startup `sync_verified_content()` detects a matching manifest hash and skips re-indexing. The startup cost becomes: one `SearchClient.get_document_count()` API call (~50ms) + manifest hash comparison.

**Manifest persistence:** Commit `data/vectorstore/ami-verified-content_manifest.json` to git (it contains only file paths, timestamps, and SHA256 hashes — no sensitive data), or mount via an Azure Files volume at `/app/data/vectorstore`.

---

## Architecture After Migration

```
Container (Azure Container Service)
├── FastAPI backend (~150MB RAM)
├── Docling (PyTorch present but NOT loaded — lazy, blocked by manifest check)
└── No ChromaDB, No HuggingFace model

External Services
├── OpenAI API — text-embedding-3-small (~$0.001/reindex, negligible)
└── Azure AI Search Free tier ($0/month)
    ├── ami-verified-content  (permanent course materials)
    └── ami-web-results       (cross-user web search cache)
```

---

## Notes & Known Limitations

- **Web result accumulation:** `ami-web-results` accumulates across restarts and all users — intentional caching. Without deduplication, repeated searches for the same query add duplicate chunks. Monitor index size via Azure portal. Free tier's 50MB cap is the practical ceiling.
- **PyTorch remains in container image:** Even after removing HuggingFace packages, Docling installs PyTorch as a transitive dependency. Container image size stays large (~2–3 GB), but PyTorch/Docling models are never loaded into RAM at runtime. OOM is fixed; image size is a separate concern.
- **Local dev requirement:** `AZURE_SEARCH_ENDPOINT` and `AZURE_SEARCH_KEY` must be present in `backend/.env` for local development. Without these, the app crashes on startup.
- **`langchain-community` alpha removed:** Pinned version was `1.0.0a1`. Upgraded to `>=0.3.0,<1.0.0` for a stable `AzureSearch` export.
