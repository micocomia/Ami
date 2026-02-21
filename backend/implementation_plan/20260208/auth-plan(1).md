# Plan: Backend-First Login/Registration System

## Context

The app has no authentication. `userId` is hardcoded to `"TestUser"` and the login button in `topbar.py` is disabled. The user wants a working login/registration page shown at the very start, with logic handled in the backend so it's reusable when the frontend is rewritten in React.

`bcrypt` and `PyJWT` are already in backend dependencies. No new packages needed.

Additionally, `store.py` (created earlier at `backend/store.py`) should be relocated to `backend/utils/store.py` to match the convention that utility modules live in `backend/utils/`.

## Files to create

- **`backend/utils/auth_store.py`** — User credential persistence (JSON file-backed, same pattern as `store.py`)
- **`backend/utils/auth_jwt.py`** — JWT token creation/verification

## Files to move

- **`backend/store.py` → `backend/utils/store.py`** — Relocate existing store module into utils

## Files to modify

- **`backend/main.py`** — Update `store` import path, add `auth_store`/`auth_jwt` imports, add `/auth/register`, `/auth/login`, `/auth/me` endpoints, load `auth_store` at startup
- **`backend/api_schemas.py`** — Add `AuthRegisterRequest`, `AuthLoginRequest` schemas
- **`backend/.env.example`** — Document `JWT_SECRET` env var
- **`frontend/utils/request_api.py`** — Add `auth_register()` and `auth_login()` helper functions
- **`frontend/utils/state.py`** — Per-user data file isolation in `_get_data_store_path()`
- **`frontend/components/topbar.py`** — Replace disabled login dialog with working Login/Register tabs; update `logout()` to clear user state
- **`frontend/main.py`** — Add auth gate before navigation (`st.stop()` if not logged in)

## Step-by-step

### Step 1: Move `backend/store.py` → `backend/utils/store.py`

Move the file. Then update the import in `backend/main.py` from `import store` to `from utils import store`.

### Step 2: `backend/utils/auth_store.py` (new)

Mirrors `utils/store.py` pattern. Stores users in `backend/data/users.json` (already gitignored).

- `_users: Dict[str, Dict]` keyed by username
- `load()` — read from disk at startup
- `create_user(username, password)` — hash with `bcrypt.hashpw()`, flush to disk, raise `ValueError` if exists
- `verify_password(username, password)` — `bcrypt.checkpw()` against stored hash
- `get_user(username)` — lookup
- `delete_user(username)` — remove user from `_users` dict, flush to disk, return `True` if user existed / `False` otherwise
- Thread lock on writes

### Step 3: `backend/utils/auth_jwt.py` (new)

- `JWT_SECRET` from `os.environ.get("JWT_SECRET", "dev-secret-change-in-production")`
- `create_token(username)` — `jwt.encode()` with 24h expiry, `sub` = username
- `verify_token(token)` — `jwt.decode()`, returns username or `None`

### Step 4: `backend/api_schemas.py`

Add after existing schemas:

- `AuthRegisterRequest(BaseModel)` — `username: str`, `password: str`
- `AuthLoginRequest(BaseModel)` — `username: str`, `password: str`

### Step 5: `backend/main.py`

- Change `import store` → `from utils import store`
- Import `from utils import auth_store, auth_jwt`
- Add `auth_store.load()` to existing `_load_stores()` startup event
- Add endpoints after CORS middleware block:
  - `POST /auth/register` — validate (username >= 3 chars, password >= 6 chars), call `auth_store.create_user()`, return JWT + username
  - `POST /auth/login` — call `auth_store.verify_password()`, return JWT + username
  - `GET /auth/me` — verify JWT from `authorization` header, return username (React readiness; Streamlit won't use this)
  - `DELETE /auth/user` — verify JWT from `authorization` header, delete user credentials via `auth_store.delete_user()`, delete all associated data (profiles, events, user state) via `store.delete_all_user_data()`, return `{"ok": True}`

### Step 5b: `backend/utils/store.py` — Add `delete_all_user_data()`

Add a function that removes all data associated with a user under a single lock:
- Remove profiles keyed as `"user_id:goal_id"` by prefix match, flush
- Remove events entry for the user, flush
- Remove user state entry for the user, flush

### Step 6: `backend/.env.example`

Append `JWT_SECRET=change-me-to-a-random-string-in-production`

### Step 7: `frontend/utils/request_api.py`

- Add `"auth_register"` and `"auth_login"` to `API_NAMES` dict
- Add `auth_register(username, password)` and `auth_login(username, password)` functions using `make_post_request()`

### Step 8: `frontend/utils/state.py`

Change `_get_data_store_path()` (line 38-39) to use per-user filenames:
```python
def _get_data_store_path():
    user_id = st.session_state.get("userId", "default")
    return Path(__file__).resolve().parents[1] / "user_data" / f"data_store_{user_id}.json"
```

Each user gets their own local state file (e.g., `data_store_alice.json`).

### Step 9: `frontend/components/topbar.py`

Replace the disabled `login()` dialog (lines 10-22) with a working Login/Register tabbed dialog:
- **Login tab**: username + password fields, calls `auth_login()`, sets `logged_in=True` and `userId` on success
- **Register tab**: username + password + confirm fields, calls `auth_register()`, auto-logs in on success

Update `logout()` (lines 24-29) to also reset `userId`, `if_complete_onboarding`, and `goals` to prevent data leakage between users.

### Step 10: `frontend/main.py`

Add auth gate after line 17 (after CSS), before the onboarding redirect (line 19):
```python
if not st.session_state.get("logged_in", False):
    # show login/register button that opens the topbar login dialog
    st.stop()
```

This blocks all navigation until the user is authenticated.

## Tests (`backend/tests/test_store_and_auth.py`)

Unit tests cover:

**`TestAuthStore`** — user creation, password verification, duplicate rejection, disk persistence, plus:
- `test_delete_user` — create user, delete, verify `get_user` returns `None`
- `test_delete_user_nonexistent_returns_false` — deleting unknown user returns `False`
- `test_delete_user_persisted_to_disk` — deleted user is gone from JSON file after reload

**`TestDeleteAllUserData`** — verifies `delete_all_user_data()`:
- `test_delete_all_user_data_removes_profiles` — profiles for user removed, other users' profiles unaffected
- `test_delete_all_user_data_removes_events` — events for user removed, others unaffected
- `test_delete_all_user_data_removes_user_state` — user state removed, others unaffected

Note: The `_isolate_store` fixture must also reset `_USER_STATES_PATH` and `_user_states` for user state tests.

Run: `pytest backend/tests/test_store_and_auth.py -v`

## Verification

1. Start backend, call `POST /auth/register` with `{"username": "alice", "password": "test123"}` — expect 200 with token
2. Call `POST /auth/login` with same creds — expect 200 with token
3. Call `POST /auth/register` with same username — expect 409 conflict
4. Call `POST /auth/login` with wrong password — expect 401
5. Check `backend/data/users.json` exists with hashed password
6. Call `DELETE /auth/user` with valid JWT in `Authorization: Bearer <token>` header — expect 200 `{"ok": true}`, user removed from `users.json`, all profiles/events/state for that user cleared
7. Call `DELETE /auth/user` with invalid/expired token — expect 401
8. Start frontend — should see login/register page, not onboarding
9. Register a new user, confirm redirect to onboarding
10. Complete onboarding flow, logout, login as different user — confirm separate goals/profiles
11. Check `frontend/user_data/` has separate `data_store_{username}.json` files
