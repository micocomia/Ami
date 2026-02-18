# Backend: Cross-Goal Profile Sync

## Context

Each goal currently has its own independent `learner_profile` with separate `cognitive_status`, `learning_preferences`, and `behavioral_patterns`. Skills mastered in Goal A (e.g., Python) are invisible when creating Goal B (e.g., Kubernetes). FSLSM preferences set in one goal don't carry to another.

This plan implements a **fully shared profile** -- like two tutors passing over what they know about the student. When a student switches goals or creates a new one, the backend merges knowledge from all existing goal profiles into the target profile.

### What's Shared vs Per-Goal

| Field | Shared? | Notes |
|-------|---------|-------|
| `mastered_skills` | Yes | Union across goals, highest proficiency wins |
| `learning_preferences` (FSLSM) | Yes | Propagated from other goals if target has none |
| `behavioral_patterns` | Yes | Propagated from other goals if target has none |
| `in_progress_skills` | Per-goal | Each goal works on different skills; newly-mastered skills are removed |
| `overall_progress` | Per-goal | Recalculated after merge: `mastered / (mastered + in_progress) * 100` |
| `learning_goal` | Per-goal | Each goal has its own objective |

## Changes Made

### Step 1: Merge Logic in Store (`utils/store.py`)

Added `_PROFICIENCY_ORDER` constant and `merge_shared_profile_fields(user_id, target_goal_id)` function:

- Calls `get_all_profiles_for_user(user_id)` to get all profiles
- Builds union of `mastered_skills` (highest proficiency per skill name wins, using `_PROFICIENCY_ORDER`)
- Propagates `learning_preferences` and `behavioral_patterns` from other goals (fills missing keys)
- Merges into target profile:
  - Adds missing mastered skills (never downgrades)
  - Overwrites `learning_preferences` and `behavioral_patterns` if target has none
  - Removes mastered skills from `in_progress_skills`
  - Recalculates `overall_progress`
- Calls `upsert_profile()` to persist
- Returns the merged profile, or `None` if no profile exists for the target goal

### Step 2: Sync Endpoint (`main.py`)

Added `POST /sync-profile/{user_id}/{goal_id}`:
- Calls `store.merge_shared_profile_fields(user_id, goal_id)`
- Returns `{"learner_profile": merged_profile}` on success
- Returns 404 if no profile exists for the target goal

### Step 3: Unit Tests (`tests/test_profile_sync.py`)

| Test | Description |
|------|-------------|
| `test_merge_no_other_goals` | Single goal -- profile returned unchanged |
| `test_merge_mastered_skills_union` | Goal A has Skill X mastered, Goal B has Skill Y -- target gets both |
| `test_merge_highest_proficiency_wins` | Same skill at "intermediate" in Goal A, "advanced" in Goal B -- "advanced" kept |
| `test_merge_preferences_propagate` | FSLSM from Goal A appears in Goal B after merge |
| `test_merge_behavioral_propagate` | behavioral_patterns from Goal A appear in Goal B |
| `test_merge_removes_mastered_from_in_progress` | Skill mastered in Goal A is removed from Goal B's in_progress_skills |
| `test_merge_recalculates_progress` | overall_progress = mastered / (mastered + in_progress) * 100 |
| `test_merge_persists` | After merge, `get_profile()` returns the merged version |
| `test_sync_endpoint_returns_merged` | `POST /sync-profile/{uid}/{gid}` returns merged profile |
| `test_sync_endpoint_404_no_profile` | Returns 404 if target goal has no profile |

All 10 tests pass.

## Files Modified

### Backend
- `utils/store.py` (modified -- added `_PROFICIENCY_ORDER`, `merge_shared_profile_fields()`)
- `main.py` (modified -- added `POST /sync-profile/{user_id}/{goal_id}` endpoint)
- `tests/test_profile_sync.py` (new -- 10 unit tests)

### Docs
- `docs/user_flows_test_plan.md` (modified -- added Flow 10: Cross-Goal Profile Sync)
