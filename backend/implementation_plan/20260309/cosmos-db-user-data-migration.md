# Implementation Plan: Migrate User Data Storage to Azure Cosmos DB

**Date:** 2026-03-09
**Branch:** beta-release-public
**Status:** Completed

---

## Context

All Ami backend storage had already been migrated to Azure (AI Search for vector store, Blob Storage for manifests/audio/diagrams). The remaining local storage was user data in 8 JSON files under `backend/data/users/`. This migration replaces those files with Azure Cosmos DB, completing the Azure-only storage strategy and enabling stateless deployment to Azure Container Instances (ACI) — the backend will be hosted on ACI while the Streamlit frontend remains on Streamlit Community Cloud.

---

## Service Selected: Azure Cosmos DB NoSQL API (Serverless Tier)

**Why Cosmos DB over Azure Table Storage:**
- Native JSON document model matches the current dict structure exactly
- Server-side `patch_item` for partial updates (Table Storage requires full entity replace)
- SQL-style `WHERE` filters for `get_all_goals_for_user(include_deleted=False)` — Table Storage cannot filter server-side
- 2 MB item size limit (vs. 1 MB for Table Storage) — safe for large `learning_content` entries
- Serverless billing = near-zero idle cost; appropriate for academic/development workloads
- Consistent with the existing Azure-first strategy

---

## Data Model

### Container Design

All containers use `/user_id` as partition key, enabling efficient single-partition reads for all user-scoped queries. Exception: `users` container uses `/username`.

| Container           | Partition Key | Cosmos `id` field                     | Replaces             |
|---------------------|---------------|---------------------------------------|----------------------|
| `users`             | `/username`   | `username`                            | `users.json`         |
| `goals`             | `/user_id`    | `"{user_id}:{goal_id}"`               | `goals.json`         |
| `profiles`          | `/user_id`    | `"{user_id}:{goal_id}"`               | `profiles.json`      |
| `profile_snapshots` | `/user_id`    | `"{user_id}:{goal_id}"`               | `profile_snapshots.json` |
| `learning_content`  | `/user_id`    | `"{user_id}:{goal_id}:{session_idx}"` | `learning_content.json` |
| `session_activity`  | `/user_id`    | `"{user_id}:{goal_id}:{session_idx}"` | `session_activity.json` |
| `mastery_history`   | `/user_id`    | `"{user_id}:{goal_id}"`               | `mastery_history.json` |
| `events`            | `/user_id`    | `user_id`                             | `events.json`        |

Containers are auto-created via `create_container_if_not_exists` on first use. No manual portal setup required.

### Goal `id` Field Type Handling

The previous implementation stored `goal["id"]` as an **integer**. Cosmos DB requires `"id"` to be a **string**. Resolution:
- Cosmos `id` stored as composite string: `"{user_id}:{goal_id}"`
- Integer goal_id stored separately as `"goal_id"` field
- `_strip_goal()` helper restores `goal["id"]` as integer on every read, preserving the existing API contract

### Array Documents

`events` and `mastery_history` store arrays in a single Cosmos item per key with an `"entries": [...]` field. Append operations use read → append → trim to 200 → upsert semantics (same as the previous file-based implementation).

---

## Files Changed

### New Files

| File | Description |
|------|-------------|
| `backend/base/cosmos_client.py` | `CosmosUserStore` wrapper class. Methods: `upsert`, `get`, `delete`, `query`, `patch` (partial updates via `patch_item`), `check_connection`, `from_env()`. All Azure SDK imports confined here. Follows the same lazy-init pattern as `blob_storage.py`. |

### Rewritten Files

| File | Description |
|------|-------------|
| `backend/utils/store.py` | Removed: in-memory dicts, `threading.Lock`, file paths, `_flush_json()`. `load()` now initialises the Cosmos client and runs a connection check. All CRUD operations delegate to `_get_cosmos()`. Profile reads strip routing fields (`id`, `user_id`, `goal_id`) to maintain backward compatibility. |
| `backend/utils/auth_store.py` | Parallel rewrite to `store.py`. Credentials stored in the `users` container. `load()` initialises the shared Cosmos client. |
| `backend/tests/conftest.py` | Added `FakeCosmosUserStore` (in-memory dict-backed fake) and `_isolate_cosmos_stores` autouse fixture. Both `store._cosmos` and `auth_store._cosmos` are set to the same fake instance per test. |

### Updated Files

| File | Change |
|------|--------|
| `backend/requirements.txt` | Added `azure-cosmos>=4.3.0` (4.3.0+ required for `patch_item`) |
| `backend/.env.example` | Added `AZURE_COSMOS_CONNECTION_STRING` |
| `backend/config/default.yaml` | Added `cosmos:` block with `database_name` |
| `backend/config/schemas.py` | Added `BlobStorageConfig` and `CosmosConfig` dataclasses to `AppConfig` |
| `backend/docker/Dockerfile` | Removed `RUN mkdir -p data/users data/vectorstore` (no local state needed) |
| `backend/docker/docker-compose.yml` | Removed `../data:/app/data` volume mount; kept `../resources:/app/resources` |
| `backend/main.py` | Added `FRONTEND_ORIGIN` env var support to CORS middleware (comma-separated origins) |
| `backend/tests/test_store_and_auth.py` | Removed disk-persistence tests and old fixture; kept all functional CRUD/auth tests |
| All 11 other test files with `_isolate_store` | Removed old fixture definitions (replaced by conftest.py autouse); updated `def client(_isolate_store)` → `def client()` where needed |

---

## Key Design Decisions

### Remove In-Memory Cache
The previous implementation loaded all data into memory at startup and flushed to disk on every write. This was a single-process optimisation incompatible with ACI (which may restart containers). The Cosmos SDK is low-latency enough (~5–15 ms) that direct reads are acceptable.

### Thread Safety
`threading.Lock` removed. The Cosmos SDK handles concurrent HTTP requests natively. A known limitation: concurrent `create_goal()` calls for the same user could generate duplicate `goal_id` values (race in `_next_goal_id_for_user` + upsert). Acceptable at academic scale.

### Profile Routing Field Stripping
Routing fields injected for Cosmos partitioning (`id`, `user_id`, `goal_id`) are stripped from profile reads via `_strip_profile()`. This preserves backward compatibility — callers that store `{"goal": "Python"}` get back `{"goal": "Python"}`, not `{"goal": "Python", "id": "alice:0", "user_id": "alice", "goal_id": 0}`.

### Graceful Degradation
`load()` logs a warning and sets `_cosmos = None` if `AZURE_COSMOS_CONNECTION_STRING` is not set. First actual store operation raises `RuntimeError`. This mirrors the pattern in `blob_storage.py`.

### patch_goal Uses Cosmos Partial Update
`patch_goal()` uses `patch_item` (Cosmos partial document update API) to avoid a read-modify-write cycle. Operations are `{"op": "set", "path": "/<field>", "value": v}` dicts. Requires `azure-cosmos>=4.3.0`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_COSMOS_CONNECTION_STRING` | Yes | Primary connection string from the Cosmos DB account Keys blade |
| `FRONTEND_ORIGIN` | Recommended for prod | Comma-separated allowed origins for CORS, e.g. `https://your-app.streamlit.app`. Defaults to `*`. |

---

## Azure Setup (One-Time)

1. In Azure Portal → Create Resource → Azure Cosmos DB → NoSQL → **Serverless** capacity mode
2. Name: `ami-cosmos`, same resource group `ami-rg`, same region as AI Search and Blob Storage
3. Navigate to **Keys** → copy **Primary Connection String**
4. Add to `backend/.env`: `AZURE_COSMOS_CONNECTION_STRING=AccountEndpoint=...`

No need to manually create the database or containers — they are created automatically on first request.

---

## ACI Deployment (Next Step)

With all storage fully in Azure, the backend container is stateless. Required ACI environment variables:

```
OPENAI_API_KEY=sk-...
JWT_SECRET=<random-64-char-string>
AZURE_SEARCH_ENDPOINT=https://<name>.search.windows.net
AZURE_SEARCH_KEY=<admin-key>
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_COSMOS_CONNECTION_STRING=AccountEndpoint=https://<acct>.documents.azure.com:443/;AccountKey=<key>==;
FRONTEND_ORIGIN=https://<your-app>.streamlit.app
ENVIRONMENT=prod
```

No volume mounts needed. Build and push the Docker image to Azure Container Registry, then deploy to ACI.

---

## Migration Path

No data migration script. Local JSON files under `backend/data/users/` remain gitignored and are ignored by the new code. Users re-register on first use against the new Cosmos DB backend. Acceptable for the academic/development context — no production user base exists.

---

## Verification

```bash
# 1. Unit tests (uses FakeCosmosUserStore, no real Cosmos needed)
cd backend && python -m pytest tests/ -q
# Expected: 513 passed

# 2. Local integration (requires real AZURE_COSMOS_CONNECTION_STRING in .env)
uvicorn main:app --reload
# POST /v1/auth/register, POST /v1/auth/login, POST /v1/goals/{user_id}
# Verify items appear in Azure Portal → Cosmos DB → Data Explorer

# 3. Docker build
docker compose -f docker/docker-compose.yml up --build
# Confirm startup logs show Cosmos DB connection OK; no volume errors
```
