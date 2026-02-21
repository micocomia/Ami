# Frontend: Cross-Goal Profile Sync

## Context

The frontend previously treated each goal's profile as fully independent. When a user switched goals or created a new one, mastered skills and learning preferences from other goals were not carried over. The skill gap identification also had no awareness of skills already mastered in other goals, leading to redundant gap flags.

This plan integrates the backend's new `POST /sync-profile/{user_id}/{goal_id}` endpoint into the frontend to:

1. Sync profiles on goal switch (shared mastered skills + preferences propagate)
2. Sync profiles on new goal creation (inherit from existing goals)
3. Augment skill gap identification with cross-goal mastery (prevent flagging already-mastered skills)

## Changes Made

### Step 1: API Helper (`frontend/utils/request_api.py`)

Added `sync_profile(user_id, goal_id)`:
- Calls `POST /sync-profile/{user_id}/{goal_id}` on the backend
- Returns the merged `learner_profile` dict on success, `None` on failure
- Uses 30-second timeout, catches all exceptions silently (non-blocking)

### Step 2: Sync on Goal Switch (`frontend/utils/state.py`)

In `change_selected_goal_id()`, after setting status flags and before persisting:
- Calls `sync_profile(user_id, new_goal_id)` if the goal has a learner_profile
- Updates both the goal dict and `st.session_state["learner_profile"]` with the merged result
- Non-blocking: if sync fails, the original profile is retained

### Step 3: Sync on New Goal Creation (`frontend/pages/skill_gap.py`)

After creating a new goal's profile via `create_learner_profile()` and before calling `add_new_goal()`:
- Calls `sync_profile(user_id, new_gid)` to inherit shared fields from existing goals
- Updates `goal["learner_profile"]` with the merged result
- Non-blocking: if sync fails, the freshly-created profile is used as-is

### Step 4: Cross-Goal Mastery in Skill Gap Identification (`frontend/components/gap_identification.py`)

In `render_identifying_skill_gap()`, before calling `identify_skill_gap()`:
- Gathers mastered skills from all existing goals in `st.session_state["goals"]`
- Builds a deduplicated map of skill name -> skill dict
- Appends a structured note to `learner_information` listing all already-mastered skills with their proficiency levels
- The note instructs the LLM to NOT list these as skill gaps

## Files Modified

- `frontend/utils/request_api.py` (modified -- added `sync_profile()` function)
- `frontend/utils/state.py` (modified -- added sync call in `change_selected_goal_id()`)
- `frontend/pages/skill_gap.py` (modified -- added sync call after profile creation)
- `frontend/components/gap_identification.py` (modified -- augmented skill gap identification with cross-goal mastery)
