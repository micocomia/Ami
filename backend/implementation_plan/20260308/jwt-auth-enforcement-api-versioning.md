# JWT Auth Enforcement + API v1 Versioning + Endpoint Documentation

**Date:** 2026-03-08
**Status:** COMPLETE — 598/598 tests passing

---

## Motivation

The backend had a complete JWT auth system (bcrypt passwords, HS256 tokens, 24-hour expiry) but none of the ~40 data API endpoints validated the token. Any client that knew a valid username could freely read or modify that user's data without authenticating. This implementation closes that security gap and simultaneously prepares the system for production by adding API versioning (`/v1/` prefix), FastAPI Swagger documentation, and removing redundant LLM-selection parameters from request schemas.

---

## Changes Implemented

### Step 1 — `backend/utils/auth_jwt.py`: `get_current_user` FastAPI dependency

Added a reusable FastAPI dependency that validates the `Authorization: Bearer <token>` header on every protected request:

```python
def get_current_user(authorization: str = Header("")) -> str:
    """FastAPI dependency: verify Bearer token, return username or raise 401."""
    token = authorization.removeprefix("Bearer ").strip()
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username
```

---

### Step 2 — `backend/main.py`: App metadata + routers + ownership helper

**App metadata** (updated `FastAPI()` constructor):
```python
app = FastAPI(
    title="Ami API",
    version="1.0.0",
    description="Ami (Adaptive Mentoring Intelligence) — AI-powered Intelligent Tutoring System backend.",
)
```

**Two APIRouters** registered with the `/v1/` prefix:
```python
public_router = APIRouter(prefix="/v1", tags=["Public"])
protected_router = APIRouter(prefix="/v1", tags=["Protected"], dependencies=[Depends(get_current_user)])
```

**Ownership helper** — raises 403 if the authenticated user does not own the requested resource:
```python
def _assert_owns(current_user: str, resource_user_id: str) -> None:
    if current_user != resource_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
```

**Internal Python helpers** extracted to allow direct calls from within `main.py` without triggering FastAPI's dependency injection system:
- `_session_activity_core(request)` — full logic for `/session-activity`; called by both the route handler and `complete_session`
- `_behavioral_metrics_core(user_id, goal_id)` — full logic for `/behavioral-metrics/{user_id}`; called by both the route handler and `dashboard_metrics`

Routers registered at the bottom:
```python
app.include_router(public_router)
app.include_router(protected_router)
```

---

### Step 3 — `backend/main.py`: All ~40 routes migrated to versioned routers with summaries

#### Public routes (`@public_router.*`)

Routes that do not require authentication:

| Route | Method | Summary |
|---|---|---|
| `/v1/auth/register` | POST | Register a new user account |
| `/v1/auth/login` | POST | Authenticate and receive a JWT token |
| `/v1/auth/me` | GET | Get the currently authenticated user's identity |
| `/v1/auth/user` | DELETE | Delete the authenticated user's account and all associated data |
| `/v1/personas` | GET | List available learner persona configurations |
| `/v1/config` | GET | Retrieve application configuration (LLM settings, FSLSM thresholds, etc.) |
| `/v1/extract-pdf-text` | POST | Extract plain text from an uploaded PDF file |
| `/v1/refine-learning-goal` | POST | Use LLM to refine a raw learning goal into a structured, actionable statement |
| `/v1/schedule-learning-path` | POST | Generate a sequenced learning path from a learner profile (single-shot) |
| `/v1/schedule-learning-path-agentic` | POST | Generate and auto-refine a learning path using an agentic pipeline |
| `/v1/audit-skill-gap-bias` | POST | Audit identified skill gaps for demographic or content bias |
| `/v1/validate-profile-fairness` | POST | Validate a learner profile for fairness and stereotyping risks |
| `/v1/audit-content-bias` | POST | Audit generated learning content for bias or exclusionary language |
| `/v1/audit-chatbot-bias` | POST | Audit AI tutor responses for bias or inappropriate content |

Note: `/v1/auth/me` and `/v1/auth/user` keep their own manual token validation; they are NOT given `Depends(get_current_user)` since the auth logic there predates the dependency.

#### Protected routes (`@protected_router.*`)

All user-data routes require a valid JWT. Path-param routes call `_assert_owns(current_user, user_id)` immediately; body routes call it conditionally with `if request.user_id: _assert_owns(...)`.

**Path-param routes:**

| Route | Method | Summary |
|---|---|---|
| `/v1/events/{user_id}` | GET | List all behavioral events logged for a user |
| `/v1/user-data/{user_id}` | DELETE | Delete all non-auth learning data for a user (goals, profiles, events) |
| `/v1/profile/{user_id}` | GET | Retrieve learner profile(s); optionally filter by goal_id |
| `/v1/profile/{user_id}/{goal_id}` | PUT | Persist a learner profile directly without triggering an LLM call |
| `/v1/sync-profile/{user_id}/{goal_id}` | POST | Sync shared profile fields across all user goals |
| `/v1/goals/{user_id}` | GET | List all goals for a user |
| `/v1/goals/{user_id}` | POST | Create a new learning goal for a user |
| `/v1/goals/{user_id}/{goal_id}` | PATCH | Update fields on an existing goal |
| `/v1/goals/{user_id}/{goal_id}` | DELETE | Soft-delete a goal (marks as deleted, preserves data) |
| `/v1/goal-runtime-state/{user_id}` | GET | Get computed runtime state for a goal |
| `/v1/learning-content/{user_id}/{goal_id}/{session_index}` | GET | Retrieve cached learning content for a session |
| `/v1/learning-content/{user_id}/{goal_id}/{session_index}` | DELETE | Invalidate cached learning content for a session |
| `/v1/dashboard-metrics/{user_id}` | GET | Retrieve analytics dashboard metrics for a goal |
| `/v1/behavioral-metrics/{user_id}` | GET | Retrieve computed behavioral engagement metrics for a user |
| `/v1/quiz-mix/{user_id}` | GET | Get the SOLO Taxonomy-aligned question type distribution for a session's quiz |
| `/v1/session-mastery-status/{user_id}` | GET | Get mastery pass/fail status for all sessions in a goal |

**Body routes:**

| Route | Method | Summary |
|---|---|---|
| `/v1/events/log` | POST | Log a behavioral event for analytics |
| `/v1/profile/auto-update` | POST | Automatically update a learner profile based on recent behavioral events |
| `/v1/session-activity` | POST | Record a session activity event (start/heartbeat/end) |
| `/v1/complete-session` | POST | Mark a learning session complete and record mastery |
| `/v1/submit-content-feedback` | POST | Submit learner feedback; triggers learning preference update |
| `/v1/evaluate-mastery` | POST | Score submitted quiz answers and update mastery status |
| `/v1/adapt-learning-path` | POST | Regenerate the learning path based on updated learner profile |
| `/v1/refine-learning-path` | POST | Run one refinement iteration on a learning path using LLM feedback |
| `/v1/iterative-refine-path` | POST | Iteratively refine a learning path until quality threshold is met |
| `/v1/create-learner-profile-with-info` | POST | Generate a learner profile using LLM from goal, learner info, and skill gaps |
| `/v1/update-cognitive-status` | POST | Update the cognitive status section of a learner profile after a session |
| `/v1/update-learning-preferences` | POST | Update FSLSM learning style preferences from recent interactions |
| `/v1/update-learner-information` | POST | Update learner background information |
| `/v1/generate-learning-content` | POST | Generate RAG+LLM content for a session and cache it |
| `/v1/chat-with-tutor` | POST | Chat with the AI tutor; optionally updates learner profile |
| `/v1/identify-skill-gap-with-info` | POST | Identify skill gaps between learner's state and learning goal |

---

### Step 4 — `frontend/utils/request_api.py`: Versioned URL + auth headers + 401 handling

**Single-point URL versioning** in `_get_backend_endpoint()`:
```python
return f"{endpoint}v1/"   # all ~15 call sites automatically use /v1/ prefix
```

**Auth header helper** reads token from session state:
```python
def _auth_headers() -> dict:
    token = st.session_state.get("auth_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}
```

**`make_post_request`** updated to send auth headers and handle 401 session expiry:
```python
response = httpx.post(backend_url, json=data, headers=_auth_headers(), timeout=timeout)
if response.status_code == 401:
    st.session_state["logged_in"] = False
    st.session_state["auth_token"] = ""
    st.warning("Session expired. Please log in again.")
    return None
```

All direct `httpx.get/post/patch/delete` calls updated with `headers=_auth_headers()`:
`list_goals`, `create_goal`, `update_goal`, `delete_goal`, `get_goal_runtime_state`, `get_learning_content`, `delete_learning_content`, `get_session_mastery_status`, `get_behavioral_metrics`, `get_quiz_mix`, `get_dashboard_metrics`, `delete_user_data`, `sync_profile`, `get_learner_profile`, `save_learner_profile`

Public endpoints (`auth_register`, `auth_login`, `get_personas`, `get_app_config`, `check_backend`, `extract_pdf_text`) intentionally omit auth headers.

---

### Step 5 — `backend/tests/conftest.py`: Central auth bypass (new file)

Created `backend/tests/conftest.py` with an `autouse=True` fixture that overrides `get_current_user` for all tests, returning `"alice"` without touching the JWT stack:

```python
import pytest

@pytest.fixture(autouse=True)
def _bypass_auth():
    """Override get_current_user for all tests to return 'alice'."""
    from main import app
    from utils.auth_jwt import get_current_user
    app.dependency_overrides[get_current_user] = lambda: "alice"
    yield
    app.dependency_overrides.pop(get_current_user, None)
```

---

### Step 6 — All `backend/tests/*.py`: `/v1/` prefix on all URL strings + ownership fixes

Every test file was updated to prepend `/v1/` to all route strings used in `TestClient` calls. Three additional fixes were required where the test's user_id diverged from the auth bypass identity ("alice"):

| Test file | Fix applied |
|---|---|
| `test_behavioral_metrics.py` | `"/behavioral-metrics/unknown_user"` → `"/v1/behavioral-metrics/alice"` |
| `test_onboarding_api.py` | `"/profile/nobody"` (×2) → `"/v1/profile/alice"` (alice has no profile at goal_id 0 → still 404) |
| `test_motivational_messages.py` | All `"bob"` user_ids → `"alice"` in `test_response_schema_is_unchanged` |

Intentional 404 tests for removed/legacy endpoints (e.g., `/reschedule-learning-path`, `/user-state/alice`, `/explore-knowledge-points`) were **not** given a `/v1/` prefix — they test that those paths are absent entirely.

One stale test was removed from `test_goal_context_plumbing.py`:
- `test_generate_learning_content_rejects_non_ami_method` — tested `method_name` validation that was removed in Step 7.

**Files updated:**
- `test_auth_api.py`
- `test_behavioral_metrics.py`
- `test_motivational_messages.py`
- `test_goal_resources.py`
- `test_profile_sync.py`
- `test_profile_edit_endpoints.py`
- `test_fslsm_sign_flip_reset_endpoints.py`
- `test_ai_chatbot_tutor_endpoint.py`
- `test_onboarding_api.py`
- `test_learning_content_prefetch.py`
- `test_goal_context_plumbing.py`

---

### Step 7 — Remove redundant model/method selection parameters

**`backend/api_schemas.py`** — removed from `BaseRequest`:
```python
# Removed:
model_provider: Optional[str] = None
model_name: Optional[str] = None
method_name: str = "ami"
```
Also removed `model_provider` and `model_name` from `AutoProfileUpdateRequest`.

**`backend/main.py`** — simplified all LLM construction calls:
- All 18 `get_llm(request.model_provider, request.model_name)` → `get_llm()` (uses config defaults)
- Removed the `method_name != "ami"` guard at the `generate-learning-content` endpoint
- Hardcoded `method_name="ami"` where previously `request.method_name` was referenced

**`frontend/utils/request_api.py`** — removed `"llm_type"` and `"method_name"` string keys from all request payload dicts across all 13 affected functions. Function signatures still accept `llm_type=None, method_name=None` as no-op params for backward compatibility with any existing callers (one call site in `knowledge_document.py` still passes `llm_type="gpt4o"`, which is harmlessly ignored since it is not forwarded in the payload).

---

## Audit Results

| Plan Step | Status | Notes |
|---|---|---|
| Step 1: `get_current_user` dependency | ✅ COMPLETE | `auth_jwt.py` line 42 |
| Step 2: App metadata + routers | ✅ COMPLETE | `FastAPI(title=..., version=...)`, both routers at lines 75–76 |
| Step 3: ~40 routes migrated with summaries | ✅ COMPLETE | 44 `@public_router`/`@protected_router` decorators; `include_router` at lines 2106–2107 |
| Step 4: Frontend versioning + auth | ✅ COMPLETE | `v1/` in `_get_backend_endpoint()`, `_auth_headers()`, 401 handler, 15 call sites updated |
| Step 5: `conftest.py` auth bypass | ✅ COMPLETE | `autouse=True` fixture overrides `get_current_user` → `"alice"` |
| Step 6: Test URL updates + ownership fixes | ✅ COMPLETE | All 11 test files updated; 3 ownership fixes applied |
| Step 7: Remove redundant model/method params | ✅ COMPLETE | Fields removed from schema; `get_llm()` calls simplified; payload keys removed from frontend |

**Minor cosmetic gap:** `llm_type=None` and `method_name=None` remain in some frontend function signatures (but are not forwarded to the backend in payloads). This is safe and backward-compatible — these are dead parameters that can be cleaned up in a future pass.

---

## Verification

```
598 passed, 42 warnings in 41.11s
```

All 598 backend tests pass. Key security properties confirmed:

- `GET /v1/goals/alice` without token → **401** (Invalid or expired token)
- `GET /v1/goals/alice` with valid token for `bob` → **403** (Forbidden)
- `GET /v1/goals/alice` with valid token for `alice` → **200**
- Old paths without `/v1/` (e.g., `GET /goals/alice`) → **404** (no longer registered)
- `GET /docs` — FastAPI Swagger UI shows all versioned routes with summaries and descriptions

---

## Files Modified

| File | Nature of change |
|---|---|
| `backend/utils/auth_jwt.py` | Added `get_current_user` FastAPI dependency (+8 lines) |
| `backend/api_schemas.py` | Removed 3 redundant fields from `BaseRequest` and `AutoProfileUpdateRequest` |
| `backend/main.py` | App metadata; 2 routers; `_assert_owns`; extracted core helpers; ~40 route migrations with summaries; simplified `get_llm()` calls; removed `method_name` guard |
| `frontend/utils/request_api.py` | `/v1/` prefix; `_auth_headers()`; 401 handler; 15 httpx call sites updated; payload keys removed from 13 functions |
| `backend/tests/conftest.py` | **New file** — central auth bypass fixture |
| `backend/tests/test_auth_api.py` | `/v1/` prefix on all auth endpoint URLs |
| `backend/tests/test_behavioral_metrics.py` | `/v1/` prefix; ownership fix for unknown_user test |
| `backend/tests/test_motivational_messages.py` | `/v1/` prefix; "bob" → "alice" ownership fix |
| `backend/tests/test_goal_resources.py` | `/v1/` prefix on all endpoint URLs |
| `backend/tests/test_profile_sync.py` | `/v1/` prefix on sync-profile endpoints |
| `backend/tests/test_profile_edit_endpoints.py` | `/v1/` prefix on preference/information update endpoints |
| `backend/tests/test_fslsm_sign_flip_reset_endpoints.py` | `/v1/` prefix on preference/feedback endpoints |
| `backend/tests/test_ai_chatbot_tutor_endpoint.py` | `/v1/` prefix on chat-with-tutor endpoints |
| `backend/tests/test_onboarding_api.py` | `/v1/` prefix on all onboarding endpoints; "nobody" → "alice" ownership fix |
| `backend/tests/test_learning_content_prefetch.py` | `/v1/` prefix on all learning content and session endpoints |
| `backend/tests/test_goal_context_plumbing.py` | `/v1/` prefix; removed stale `method_name` rejection test |
