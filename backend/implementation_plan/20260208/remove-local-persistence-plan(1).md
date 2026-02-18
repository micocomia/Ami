# Plan: Replace local file persistence with backend API

## Context

The frontend currently persists all user state (goals, onboarding status, chat history, document caches, etc.) to local JSON files in `frontend/user_data/data_store_{userId}.json`. This means user data is device-specific — logging in from a different device loses all progress. The backend already stores auth credentials, learner profiles, and events, but not the full UI state. We will add a generic user-state endpoint to the backend and replace all local file I/O in the frontend with HTTP calls.

## Backend changes

### 1. Add user state storage to `backend/utils/store.py`

Add a new in-memory dict `_user_states` backed by `backend/data/user_states.json`, following the same pattern as `_profiles` and `_events`:

- `_USER_STATES_PATH = _DATA_DIR / "user_states.json"`
- `_user_states: Dict[str, Dict[str, Any]] = {}`
- Update `load()` to also load `user_states.json`
- Add `_flush_user_states()` — writes to disk
- Add `get_user_state(user_id) -> Optional[Dict]`
- Add `put_user_state(user_id, state: Dict)` — upsert with lock + flush
- Add `delete_user_state(user_id)` — remove with lock + flush

### 2. Add endpoints to `backend/main.py`

Three new endpoints:

- `GET /user-state/{user_id}` → returns `{ "state": {...} }` or 404
- `PUT /user-state/{user_id}` → body `{ "state": {...} }`, saves and returns `{ "ok": true }`
- `DELETE /user-state/{user_id}` → clears user state, returns `{ "ok": true }`

No auth required (consistent with existing endpoints like `/profile/{user_id}`).

### 3. Add schema to `backend/api_schemas.py`

- `UserStateRequest(BaseModel)` with field `state: Dict[str, Any]`

## Frontend changes

### 4. Add API functions in `frontend/utils/request_api.py`

- `get_user_state(backend_endpoint, user_id) -> (status, data)`
- `save_user_state(backend_endpoint, user_id, state) -> (status, data)`
- `delete_user_state(backend_endpoint, user_id) -> (status, data)`

### 5. Rewrite `frontend/utils/state.py` persistence functions

- **Remove** `_get_data_store_path()` entirely
- **Remove** `backend_endpoint` and `available_models` from `PERSIST_KEYS` (these are derived from config/backend, not user data)
- **Rewrite `load_persistent_state()`**: call `get_user_state()` via HTTP GET instead of reading local file
- **Rewrite `save_persistent_state()`**: call `save_user_state()` via HTTP PUT instead of writing local file. Add a timestamp-based debounce (max 1 save per second) to avoid excessive HTTP calls — the dozens of save calls scattered through the codebase will mostly no-op, with the final save at the end of `main.py` catching everything.
- Add `delete_persistent_state()`: calls `delete_user_state()` via HTTP DELETE (used by Restart Onboarding).

### 6. Update `frontend/main.py`

- Remove import of `_get_data_store_path` (already done in prior change)
- No other changes needed — existing `save_persistent_state()` / `load_persistent_state()` calls continue to work with the new implementation

### 7. Update `frontend/pages/learner_profile.py` — Restart Onboarding

Replace the local file backup/delete logic in `show_restart_onboarding_dialog()` with:
1. Call `delete_persistent_state()` (which hits `DELETE /user-state/{user_id}`)
2. Clear `st.session_state`
3. Redirect to onboarding

Remove the `_get_data_store_path` import.

### 8. Update `frontend/components/topbar.py` — Logout

The `logout()` function currently saves cleared state to `data_store_default.json`. After the rewrite, `save_persistent_state()` will POST to the backend using the "default" userId, which is fine — but we should skip the save entirely on logout since there's no point persisting cleared/default state.

- Remove the `save_persistent_state()` call from `logout()`

## Files to modify

| File | Change |
|---|---|
| `backend/utils/store.py` | Add user state CRUD functions |
| `backend/main.py` | Add 3 new endpoints |
| `backend/api_schemas.py` | Add `UserStateRequest` |
| `frontend/utils/request_api.py` | Add 3 API helper functions |
| `frontend/utils/state.py` | Rewrite persistence to use HTTP, remove `_get_data_store_path` |
| `frontend/pages/learner_profile.py` | Simplify Restart Onboarding dialog |
| `frontend/components/topbar.py` | Remove save call from `logout()` |

## Verification

1. Start backend: `cd backend && python main.py`
2. Start frontend: `cd frontend && streamlit run main.py`
3. Test login → verify state loads from backend (or empty for new user)
4. Complete onboarding → logout → login again → verify user lands on dashboard (not onboarding)
5. Test "Restart Onboarding" from profile page → verify state is cleared and user goes to onboarding
6. Check `backend/data/user_states.json` exists and contains saved state
7. Verify `frontend/user_data/` is no longer written to
