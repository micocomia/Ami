# Plan: Wire PROFILE_STORE and EVENT_STORE as Backend Source of Truth

## Context

The backend has in-memory `PROFILE_STORE` and `EVENT_STORE` dicts with endpoints that are never used by the frontend. The frontend uses older stateless endpoints (`/create-learner-profile-with-info`, `/update-learner-profile`) that don't write to these stores, and manages all profile state locally in Streamlit session state + a JSON file. Since the frontend will be rewritten in React, the backend should become the authoritative store for profiles and events.

## Approach

1. Extract stores into a new `backend/store.py` module with JSON file-backed persistence
2. Make the old endpoints write-through to the store (backward-compatible via optional fields)
3. Update the frontend call sites to pass `user_id` and `goal_id`

## Files to modify

- **`backend/store.py`** (new) — persistence layer
- **`backend/main.py`** — replace in-memory dicts with store module, add write-through to old endpoints
- **`backend/api_schemas.py`** — add optional `user_id`/`goal_id` to two request schemas
- **`frontend/utils/request_api.py`** — accept and pass `user_id`/`goal_id` in profile functions
- **`frontend/pages/skill_gap.py`** — pass `user_id`/`goal_id` at profile creation (line 39)
- **`frontend/pages/learner_profile.py`** — pass `user_id`/`goal_id` at profile create (line 27) and update (line 202)
- **`frontend/pages/knowledge_document.py`** — pass `user_id`/`goal_id` at profile update (line 506)
- **`frontend/pages/goal_management.py`** — pass `user_id`/`goal_id` at profile creation (line 157)

## Step-by-step

### Step 1: Create `backend/store.py`

New module with:
- `_profiles: Dict[str, Dict]` keyed by `"{user_id}:{goal_id}"` (composite key supports multi-goal)
- `_events: Dict[str, List[Dict]]` keyed by `user_id` (events are user-level; payload can carry `goal_id`)
- `load()` — reads from `backend/data/profiles.json` and `backend/data/events.json` on startup
- `upsert_profile(user_id, goal_id, profile)` — writes to memory + flushes to disk
- `get_profile(user_id, goal_id)` — single profile lookup
- `get_all_profiles_for_user(user_id)` — returns `{goal_id: profile}` dict
- `append_event(user_id, event)` — appends + caps at 200 + flushes
- `get_events(user_id)` — returns event list
- Thread lock on writes for safety
- `backend/data/` is already in `.gitignore`

### Step 2: Modify `backend/api_schemas.py`

Add optional fields to two schemas (backward-compatible — existing calls without these fields still work):

- `LearnerProfileInitializationWithInfoRequest` (line 31): add `user_id: Optional[str] = None`, `goal_id: Optional[int] = None`
- `LearnerProfileUpdateRequest` (line 38): add `user_id: Optional[str] = None`, `goal_id: Optional[int] = None`

### Step 3: Modify `backend/main.py`

- Remove `PROFILE_STORE` and `EVENT_STORE` dict declarations (lines 32-33)
- Add `import store` and call `store.load()` via a FastAPI startup event
- Add `goal_id: int = 0` to `AutoProfileUpdateRequest` (line 49)

**Old endpoints — add write-through after existing LLM calls:**

- `/create-learner-profile-with-info` (line 249): after `initialize_learner_profile_with_llm()`, if `request.user_id` and `request.goal_id` are provided, call `store.upsert_profile()`
- `/update-learner-profile` (line 273): after `update_learner_profile_with_llm()`, if `request.user_id` and `request.goal_id` are provided, call `store.upsert_profile()`

**New endpoints — replace direct dict access with `store` module:**

- `/events/log` (line 41): use `store.append_event()` and `store.get_events()`
- `/profile/auto-update` (line 65): use `store.get_profile(user_id, goal_id)` and `store.upsert_profile()`; use `store.get_events()` for interactions
- `/profile/{user_id}` (line 153): use `store.get_profile()` or `store.get_all_profiles_for_user()`; add optional `goal_id` query param
- `/events/{user_id}` (line 160): use `store.get_events()`

### Step 4: Update frontend API functions

In `frontend/utils/request_api.py`:

- `create_learner_profile()` (line 108): add `user_id=None, goal_id=None` params; include in `data` dict when not None
- `update_learner_profile()` (line 119): add `user_id=None, goal_id=None` params; include in `data` dict when not None

### Step 5: Update frontend call sites

Pass `user_id=st.session_state.get("userId")` and the appropriate `goal_id` at each call site:

1. **`skill_gap.py:39`** — `create_learner_profile(..., user_id=..., goal_id=get_new_goal_uid())`
2. **`learner_profile.py:27`** — `create_learner_profile(..., user_id=..., goal_id=st.session_state.get("selected_goal_id"))`
3. **`learner_profile.py:202`** — `update_learner_profile(..., user_id=..., goal_id=st.session_state.get("selected_goal_id"))`
4. **`knowledge_document.py:506`** — `update_learner_profile(..., user_id=..., goal_id=st.session_state.get("selected_goal_id"))`
5. **`goal_management.py:157`** — `create_learner_profile(..., user_id=..., goal_id=get_new_goal_uid())`

Note: `knowledge_document.py:506` is inside `update_learner_profile_with_feedback()` which is called from two places (lines 141 and 497), so wiring it there covers both.

## Verification

1. Start the backend, go through the full onboarding flow (onboarding -> skill gap -> create profile)
2. Check that `backend/data/profiles.json` is created with a key like `"TestUser:0"`
3. Complete a learning session, verify the profile update is written through
4. Restart the backend server, call `GET /profile/TestUser` and verify data persists
5. Call `GET /profile/TestUser?goal_id=0` and verify single-goal retrieval works
