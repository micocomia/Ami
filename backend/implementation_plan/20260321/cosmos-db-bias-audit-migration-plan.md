# Plan: Align Sprint-7 Bias Audit Storage with Azure Cosmos DB

## Date
2026-03-21

## Context
Sprint-6/7 added bias audit persistence using local JSON files (`bias_audit_log.json`), while the rest of the team migrated all storage to Azure Cosmos DB on the `beta-release-public` branch. This change ports the two bias audit log functions to use the same Cosmos DB backend, so the sprint-7 work integrates cleanly with the team's infrastructure.

## Files Modified

### 1. `backend/base/cosmos_client.py` (new file on this branch)
- Copied from `beta-release-public` to bring Cosmos DB client infrastructure to this branch.
- Added `"bias_audit_log": "/user_id"` to the `_PARTITION_KEYS` dict so the container is auto-created on first use.
- This is the **only difference** from the beta version of this file.

### 2. `backend/utils/store.py`
Replaced the JSON-backed `append_bias_audit_log` and `get_bias_audit_log` with Cosmos DB equivalents:

- **Removed**: `_BIAS_AUDIT_LOG_PATH`, `_bias_audit_log` in-memory dict, and all JSON file references for bias audit.
- **Added**: `_cosmos` module-level variable, Cosmos DB initialization in `load()`, and `_get_cosmos()` helper.
- **`append_bias_audit_log`** — follows the same pattern as beta's `append_event`: read existing doc, append to `entries` array, cap at 200, upsert back. Cosmos `id` = `user_id`, partition key = `user_id`.
- **`get_bias_audit_log`** — read single doc by `user_id`, filter entries by `goal_id` if provided. Returns deep copies for data isolation.
- **`delete_all_user_data`** — now deletes from the `bias_audit_log` Cosmos container (with RuntimeError fallback if Cosmos is not configured).

### 3. `backend/tests/conftest.py`
- Added `FakeCosmosUserStore` class (matching beta-release-public's structure exactly).
- Added `_isolate_cosmos_stores` autouse fixture that injects the fake into `store._cosmos`.
- This alignment reduces merge conflicts when merging into beta-release-public.

### 4. `backend/tests/test_bias_audit_persistence.py`
- Removed duplicate `FakeCosmosUserStore` (now provided by conftest).
- Removed `_BIAS_AUDIT_LOG_PATH` and `_bias_audit_log` monkeypatching (no longer needed).
- Replaced `test_persistence_to_disk` with `test_cosmos_container_stores_data`.
- All 10 store-level tests pass.

## No Other Changes Needed
- `main.py` endpoints call `store.append_bias_audit_log()` and `store.get_bias_audit_log()` — signatures stayed identical.
- `api_schemas.py` — unchanged.
- React frontend components — unchanged (they consume the same API responses).

## Merge Notes for beta-release-public
When merging this branch into beta-release-public, the following conflicts are expected and require manual resolution:
- **`store.py`** — beta is fully Cosmos-backed; take beta's version and add the two bias audit functions.
- **`main.py`** — merge our `append_bias_audit_log` calls and `/v1/bias-audit-history` endpoint into beta's version.
- **`conftest.py`** — should be near-identical after this alignment; take either version.
- **`cosmos_client.py`** — only diff is the `"bias_audit_log"` partition key entry; trivial merge.
- **React frontend files** (`AnalyticsPage.tsx`, `skillGap.ts`, `HomePage.tsx`) — both branches modified; review and combine.

## Environment Requirement
`AZURE_COSMOS_CONNECTION_STRING` must be set in `.env` for bias audit log to work. Without it, `store.load()` logs a warning and audit functions raise `RuntimeError` at runtime.

## Verification
- All 10 store-level tests pass (`pytest backend/tests/test_bias_audit_persistence.py`).
- `bias_audit_log` container appears in `_PARTITION_KEYS`.
- `delete_all_user_data` includes `bias_audit_log` in cleanup.
- `cosmos_client.py` diff vs beta is exactly one added line.
