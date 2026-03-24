# Plan: Azure Blob Storage for Manifest, Audio, and Diagrams

## Context

Two problems addressed together since they share the same solution (Azure Blob Storage):

1. **Manifest fragility** — `ami-verified-content_manifest.json` lived on disk, requiring gitignore/dockerignore exceptions and manual commit steps to prevent Docling re-running on every container restart.

2. **Container bloat from generated files** — TTS audio (`.mp3`) and rendered diagrams (`.svg`) accumulate in `backend/data/audio/` and `backend/data/diagrams/` inside the container with no eviction. They survived container restarts and grew unboundedly on ACI.

Azure Blob Storage solves both cleanly: manifests are private blobs, audio/diagram files are public-read blobs served directly by their Azure CDN URL — no FastAPI static mount needed.

---

## Architecture After Migration

```
Container (Azure Container Instances)
├── No data/audio/ directory
├── No data/diagrams/ directory
└── No manifest file on disk

Azure Blob Storage
├── ami-manifests  [private]
│   └── ami-verified-content_manifest.json
├── ami-audio      [blob-level public read]
│   └── <uuid>.mp3  (served directly by Azure CDN)
└── ami-diagrams   [blob-level public read]
    └── <uuid>.svg  (served directly by Azure CDN)
```

**Frontend impact: zero** — `_absolutize_backend_url()` in `frontend/pages/knowledge_document.py` already short-circuits on absolute URLs (`https://...`), so blob URLs pass through unchanged.

---

## One-Time Azure Setup (before use)

1. Create a Storage Account in Azure portal (same resource group `ami-rg`, region `eastus`)
2. Create three blob containers:
   - `ami-manifests` — access level: **Private**
   - `ami-audio` — access level: **Blob** (public read, no listing)
   - `ami-diagrams` — access level: **Blob** (public read, no listing)
3. Copy the **Connection String** from the storage account's **Access keys** blade
4. Add `AZURE_STORAGE_CONNECTION_STRING` to `backend/.env`

---

## Files Changed

| File | Change |
|---|---|
| `backend/base/blob_storage.py` | **NEW** — thin `BlobStorageClient` wrapper with `upload()`, `download()`, `from_env()` |
| `backend/base/verified_content_manager.py` | Removed `persist_directory`; added `blob_client`/`manifests_container`; replaced `_manifest_path()`, `_load_manifest()`, `_save_manifest()` with blob equivalents |
| `backend/modules/content_generator/agents/tts_generator.py` | Removed `AUDIO_DIR`; assembles audio bytes in-memory, uploads to `ami-audio`, returns absolute blob URL |
| `backend/modules/content_generator/agents/diagram_renderer.py` | Removed `DIAGRAM_DIR`; uploads SVG to `ami-diagrams`, returns absolute blob URL |
| `backend/main.py` | Removed `StaticFiles` import and `/static/audio` + `/static/diagrams` mounts |
| `backend/requirements.txt` | Added `azure-storage-blob>=12.0.0` |
| `backend/.env.example` | Added `AZURE_STORAGE_CONNECTION_STRING` |
| `backend/config/default.yaml` | Added `blob_storage` config block; removed `persist_directory` from vectorstore |
| `backend/config/schemas.py` | Updated `EmbeddingConfig` defaults to openai; replaced `VectorstoreConfig.persist_directory` with `type` |
| `backend/.gitignore` | Reverted — removed `!data/vectorstore/` exceptions; `data/` fully excluded |
| `backend/docker/.dockerignore` | Reverted — `data/` fully excluded (was only `data/users/`) |
| `backend/tests/test_verified_content.py` | Updated `manager` fixture to use `mock_blob_client`; sync tests mock `_load_manifest`/`_save_manifest` instead of doing file I/O |

---

## Pre-Implementation Gaps Addressed

| # | Gap | Fix Applied |
|---|---|---|
| 1 | `preindex_verified_content.py` called `manager._manifest_path()` (removed) | `_manifest_path()` replaced with `_blob_manifest_name()`; preindex script uses `sync_verified_content()` which calls `_save_manifest()` internally |
| 2 | `tts_generator.py` wrote to a local file before returning URL | Bytes collected in-memory via `TemporaryDirectory`, uploaded directly to blob |
| 3 | `diagram_renderer.py` had `base_url` param that became unused | Param kept in signature (defaulted to `""`) for backwards compatibility; ignored in impl |
| 4 | Old manifest was committed to git | `data/` was never tracked (confirmed via `git ls-files data/`) — no `git rm` needed |
| 5 | `schemas.py` `EmbeddingConfig` defaults showed stale huggingface values | Updated to `openai` / `text-embedding-3-small`; `VectorstoreConfig` now has `type` field |
| 6 | `persist_directory` still referenced in `VectorStoreFactory.create()` call | Passed `persist_directory="."` as no-op to satisfy the Azure branch signature |

---

## Key Design Decisions

- **Lazy blob client init** — `_get_blob_client()` in `tts_generator.py` and `diagram_renderer.py` initializes the client on first use, avoiding import-time failures if `AZURE_STORAGE_CONNECTION_STRING` is not set during testing.
- **Graceful degradation in manifest** — if `blob_client` is `None` (no connection string), `_load_manifest()` returns `None` and `_save_manifest()` logs a warning. This causes a full re-index on every startup but does not crash.
- **Connection string over managed identity** — simplest approach for ACI. Swap to `DefaultAzureCredential` if moving to managed identity later.
- **No TTL on blobs** — audio and diagram blobs accumulate. Set up Azure Blob Storage lifecycle management policies to delete blobs older than N days.

---

## Verification Steps

1. **Run tests** — `cd backend && python -m pytest tests/test_verified_content.py -v`
2. **Run preindex script** — manifest should appear in `ami-manifests` blob container (verify in Azure portal)
3. **Rebuild Docker image** — `docker build -f ./backend/docker/Dockerfile ./backend -t ami-backend-test`
4. **Run locally** — startup should log `"skipping re-index"` (no Docling) on second run
5. **Trigger audio content** — generate content for an audio learner → verify MP3 URL in response is `https://<account>.blob.core.windows.net/ami-audio/...`
6. **Trigger diagram content** — generate content for a visual learner → verify SVG URL in markdown is `https://<account>.blob.core.windows.net/ami-diagrams/...`

---

## Out of Scope

- **User data JSON files** (`profiles.json`, `goals.json`, etc. in `backend/data/`) — migrating these requires refactoring `backend/utils/store.py`. Separate task.
- **Blob lifecycle policies** — set up via Azure portal after initial deployment.
