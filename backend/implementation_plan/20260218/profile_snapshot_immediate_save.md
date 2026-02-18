# Backend: Profile Snapshot for Immediate Saves & Correct Adapt Comparison

## Context

The system previously delayed saving the learner profile to the backend store when
`update_learning_preferences` was triggered from `learner_profile.py`. The comment
said this was to keep the backend store "old" so that the `/adapt-learning-path`
endpoint could compare old vs new FSLSM for its delta decision.

This design caused three cascading bugs:

1. **Switching goals loses the new profile**: `change_selected_goal_id()` calls
   `sync_profile()`, which reads from the backend store (still the old profile) and
   overwrites the in-memory new profile.

2. **FSLSM not propagated to new goals**: When a new goal is created and
   `sync_profile()` is called, it only sees the old FSLSM in the store.

3. **Returning to original goal shows initial state**: Same as #1 — the store has the
   old profile, so the sync overwrites whatever was in memory.

The fix is to **always save profiles immediately** and compensate by adding a
**snapshot mechanism** so `adapt_learning_path` can still compare pre-update vs
post-update FSLSM. Each preference-changing update endpoint saves the current store
profile as a snapshot before overwriting it; `adapt_learning_path` reads that snapshot
as `old_profile`.

---

## Changes Made

### Step 1 — `backend/utils/store.py`: Add snapshot storage

Added `_PROFILE_SNAPSHOTS_PATH` and `_profile_snapshots` module-level dict (keyed
identically to `_profiles`).

Extended `load()` to restore snapshots from disk (updated `global` declaration to
include `_profile_snapshots`).

Added `_flush_snapshots()` private helper.

Added three new public functions:
- `save_profile_snapshot(user_id, goal_id, profile)` — saves a pre-update snapshot under lock, flushes to disk
- `get_profile_snapshot(user_id, goal_id)` — returns snapshot or `None`
- `delete_profile_snapshot(user_id, goal_id)` — removes snapshot under lock, flushes to disk

Extended `delete_all_user_data()` to purge all snapshots for the deleted user (inside
the lock, same pattern as profiles).

### Step 2 — `backend/main.py`: Save snapshot before preference-changing updates only

`adapt_learning_path` only compares **FSLSM dimensions** (`old_fslsm` vs `new_fslsm`).
Cognitive-status updates (`/update-cognitive-status`) never change FSLSM, so saving a
snapshot there would overwrite a valid FSLSM snapshot from a prior preference update —
causing the delta to appear as 0 and suppressing adaptation. Therefore:

- **DO save snapshot**: `/update-learning-preferences` and `/update-learner-profile`
- **DO NOT save snapshot**: `/update-cognitive-status`

In both preference endpoints, immediately after `learner_profile` is parsed to a dict
and before the LLM call:

```python
# Snapshot the pre-update FSLSM state so adapt-learning-path can compare old vs new.
if request.user_id is not None and request.goal_id is not None and isinstance(learner_profile, dict):
    store.save_profile_snapshot(request.user_id, request.goal_id, learner_profile)
```

### Step 3 — `backend/main.py`: Use snapshot as `old_profile` in `/adapt-learning-path`

Replaced:
```python
old_profile = store.get_profile(request.user_id, request.goal_id) or {}
```

With:
```python
# old_profile: use snapshot (pre-update) if available; fall back to current store
old_profile = store.get_profile_snapshot(request.user_id, request.goal_id) or \
              store.get_profile(request.user_id, request.goal_id) or {}
```

Added snapshot deletion after `result_plan` is determined — in both the "keep" early
return and the normal return path — so the next adaptation baseline resets:
```python
store.delete_profile_snapshot(request.user_id, request.goal_id)
```

---

## How Each Bug Is Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Switching goals overwrites new profile | `sync_profile()` reads old store profile and overwrites in-memory new profile | New profile is now in the store immediately; sync returns the new profile |
| FSLSM not carried over to new goals | `sync_profile()` only sees old FSLSM in store | New FSLSM is now in store before `sync_profile()` is called |
| Returning to original goal shows stale/empty profile | Store had old profile; sync overwrote in-memory state | New profile persisted immediately; snapshot mechanism preserves old FSLSM for adapt comparison |
| `adapt_learning_path` losing old/new comparison | Was relying on store being stale | Now uses explicit snapshot (pre-update) vs request profile (post-update) |

---

## Tests Added (`backend/tests/test_store_and_auth.py`)

Updated `_isolate_store` fixture to include snapshot path/dict isolation.

Added `TestProfileSnapshotPersistence` class (8 tests):

| Test | Description |
|------|-------------|
| `test_save_and_get_snapshot` | Basic round-trip save and retrieve |
| `test_get_nonexistent_snapshot_returns_none` | Missing key returns `None` |
| `test_save_snapshot_does_not_affect_profile` | Snapshot and live profile are independent |
| `test_overwrite_snapshot` | Second save overwrites first |
| `test_delete_snapshot` | Deleted snapshot returns `None` |
| `test_delete_nonexistent_snapshot_is_noop` | No exception on missing key |
| `test_snapshot_persisted_to_disk` | File written correctly |
| `test_load_restores_snapshot_from_disk` | Survives simulated restart |

Added `test_delete_all_user_data_removes_snapshots` to `TestDeleteAllUserData`:
- Verifies snapshots for the deleted user are purged
- Verifies another user's snapshots are untouched

All 42 tests pass.

---

## Files Modified

- `utils/store.py` — snapshot storage, load, flush, save/get/delete, delete_all cleanup
- `main.py` — snapshot save in `/update-learning-preferences` and `/update-learner-profile`; snapshot read + delete in `/adapt-learning-path`
- `tests/test_store_and_auth.py` — fixture isolation + 9 new tests
