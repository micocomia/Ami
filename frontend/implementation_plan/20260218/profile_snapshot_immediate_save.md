# Frontend: Profile Snapshot for Immediate Saves & Correct Adapt Comparison

## Context

The system previously delayed saving the learner profile to the backend store when
`update_learning_preferences` was triggered from `learner_profile.py`. This caused
three cascading bugs:

1. **Switching goals loses the new profile**: `change_selected_goal_id()` calls
   `sync_profile()`, which reads from the backend store (still the old profile) and
   overwrites the in-memory new profile.

2. **FSLSM not propagated to new goals**: When a new goal is created and
   `sync_profile()` is called, it only sees the old FSLSM in the store.

3. **Returning to original goal shows initial state**: Same as #1 — the store has the
   old profile, so the sync overwrites whatever was in memory.

4. **`is_learner_profile_ready` set before sync**: Status flag reflected empty
   pre-sync profile, causing UI to show incorrect readiness state.

The fix is to **always save profiles immediately** (handled on the backend via snapshot
mechanism) and to **always fetch from the backend on goal switch** so the in-memory
state always reflects the source of truth.

---

## Changes Made

### Step 4 — `frontend/pages/learner_profile.py`: Remove delayed save

In `update_learner_profile_with_additional_info()`:

**Before:**
```python
# Don't pass user_id/goal_id here — avoid persisting to the profile store
# immediately, so the adapt-learning-path endpoint can still read the OLD
# profile for FSLSM delta comparison.
new_learner_profile = update_learning_preferences(old_profile, additional_info)
if new_learner_profile is not None:
    if _has_significant_fslsm_change(old_profile, new_learner_profile):
        st.session_state[f"adaptation_suggested_{goal_id}"] = True
    else:
        # No adaptation needed — persist the updated profile to the store now
        save_learner_profile(user_id, goal_id, new_learner_profile)
```

**After:**
```python
# Pass user_id/goal_id so the backend saves immediately and captures a
# pre-update snapshot for adapt-learning-path delta comparison.
new_learner_profile = update_learning_preferences(old_profile, additional_info, user_id=user_id, goal_id=goal_id)
if new_learner_profile is not None:
    if _has_significant_fslsm_change(old_profile, new_learner_profile):
        st.session_state[f"adaptation_suggested_{goal_id}"] = True
    # Profile is already persisted to the backend by update_learning_preferences.
```

Removed unused `save_learner_profile` from the import line.

### Step 4b — `frontend/utils/state.py`: Make goal switching always fetch from backend

`change_selected_goal_id()` previously skipped `sync_profile` if the in-memory
`goals[goal_id_idx]["learner_profile"]` was empty, causing stale/blank profiles to
persist uncorrected.

**Before:**
```python
# status
st.session_state["is_learner_profile_ready"] = True if st.session_state["learner_profile"] else False
st.session_state["is_learning_path_ready"] = True if st.session_state["learning_path"] else False
st.session_state["is_skill_gap_ready"] = True if st.session_state["skill_gaps"] else False
# Sync profile with shared fields from other goals
from utils.request_api import sync_profile
user_id = st.session_state.get("userId")
if user_id and goals[goal_id_idx].get("learner_profile"):   # ← guarded
    merged = sync_profile(user_id, new_goal_id)
    if merged:
        goals[goal_id_idx]["learner_profile"] = merged
        st.session_state["learner_profile"] = merged
```

**After:**
```python
st.session_state["is_learning_path_ready"] = True if st.session_state["learning_path"] else False
st.session_state["is_skill_gap_ready"] = True if st.session_state["skill_gaps"] else False
# Always fetch goal's profile from backend (source of truth) and sync shared fields.
# This ensures FSLSM/mastery changes made on other goals are reflected immediately,
# and prevents stale or empty in-memory profiles from being shown.
from utils.request_api import sync_profile
user_id = st.session_state.get("userId")
if user_id:
    merged = sync_profile(user_id, new_goal_id)
    if merged:
        goals[goal_id_idx]["learner_profile"] = merged
        st.session_state["learner_profile"] = merged
# Update ready flag AFTER sync (reflects backend-fetched profile)
st.session_state["is_learner_profile_ready"] = True if st.session_state["learner_profile"] else False
```

Key changes:
- Removed `goals[goal_id_idx].get("learner_profile")` guard — always calls `sync_profile` when `user_id` is present
- `sync_profile` returns `None` on 404 (no profile in store), in which case in-memory value is preserved — safe for new goals
- Moved `is_learner_profile_ready` update to **after** sync so it reflects the backend-fetched profile

---

## How Each Bug Is Fixed

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Switching goals overwrites new profile | `sync_profile()` reads old store profile and overwrites in-memory new profile | New profile is now in the store immediately (backend fix); sync returns the new profile |
| FSLSM not carried over to new goals | `sync_profile()` only sees old FSLSM in store | New FSLSM is in store before `sync_profile()` is called |
| Returning to original goal shows stale/empty profile | In-memory profile guard prevented backend fetch | Guard removed — always fetches from backend on goal switch |
| `is_learner_profile_ready` set before sync | Status flag reflected empty pre-sync profile | Flag update moved to after `sync_profile` call |

---

## Files Modified

- `pages/learner_profile.py` — removed delayed save; now always passes `user_id`/`goal_id` to `update_learning_preferences`; removed unused `save_learner_profile` import
- `utils/state.py` — `change_selected_goal_id()` always calls `sync_profile`; `is_learner_profile_ready` updated after sync
