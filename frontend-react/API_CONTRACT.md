# API Contract

This document is derived from the current **Streamlit frontend** (`frontend/utils/request_api.py`, `frontend/utils/backend.py`) and **FastAPI backend** (`backend/main.py`, `backend/api_schemas.py`) for use when integrating the React frontend.

**Base URL**: Configured by the frontend (e.g. `http://localhost:8000/`; trailing slash recommended).

---

## 1. Auth

### 1.1 POST `/auth/register`

- **Method**: `POST`
- **Path**: `/auth/register`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | At least 3 characters |
| `password` | string | ✅ | At least 6 characters |

Example: `{"username": "alice", "password": "secret123"}`

**Response — Success (200)**  
```json
{ "token": "<jwt>", "username": "alice" }
```

**Response — Error**  
- `400`: `{"detail": "Username must be at least 3 characters"}` or `"Password must be at least 6 characters"`.
- `409`: `{"detail": "Username already exists"}`

**Auth**: None  
**Frontend error handling**: Show `detail`; on 409 prompt that username already exists and guide to login.

---

### 1.2 POST `/auth/login`

- **Method**: `POST`
- **Path**: `/auth/login`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | ✅ | Username |
| `password` | string | ✅ | Password |

Example:`{"username": "alice", "password": "secret123"}`

**Response — Success (200)**  
```json
{ "token": "<jwt>", "username": "alice" }
```

**Response — Error**  
- `401`: `{"detail": "Invalid username or password"}`

**Auth**: None  
**Token storage**: After login/register, store `token` in memory and persist (e.g. `localStorage.auth_token`); send `Authorization: Bearer <token>` for authenticated requests.  
**Frontend error handling**: On 401 show invalid credentials; on network error prompt to check backend.

---

### 1.3 GET `/auth/me`

- **Method**: `GET`
- **Path**: `/auth/me`

**Request body**: None

**Response — Success (200)**  
```json
{ "username": "alice" }
```

**Response — Error**  
- `401`: `{"detail": "Invalid or expired token"}`

**Auth**: **JWT** — Header: `Authorization: Bearer <token>`  
**Token storage**: Same as 1.2; on 401 clear local token and **redirect to login**.  
**Frontend error handling**: 401 → clear token, redirect to login; other errors may retry once then show message.

---

### 1.4 DELETE `/auth/user`

- **Method**: `DELETE`
- **Path**: `/auth/user`

**Request body**: None

**Response — Success (200)**  
```json
{ "ok": true }
```

**Response — Error**  
- `401`: `{"detail": "Invalid or expired token"}`
- `404`: `{"detail": "User not found"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`  
**Frontend error handling**: On success clear token and redirect to login/home; 401 same as 1.3; 404 prompt user not found.

---

## 2. Config and static data

### 2.1 GET `/config`

- **Method**: `GET`
- **Path**: `/config`

**Request body**: None

**Response — Success (200)**  
Returns app config object, including but not limited to:

- `skill_levels`: string[]
- `default_session_count`: number
- `default_llm_type`: string
- `default_method_name`: string
- `motivational_trigger_interval_secs`: number
- `max_refinement_iterations`: number
- `mastery_threshold_default`: number
- `mastery_threshold_by_proficiency`: Record<string, number>
- `quiz_mix_by_proficiency`: Record<string, QuizMix>
- `fslsm_thresholds`: Record<string, FslsmDimensionConfig>

**Response — Error**: None (current implementation does not return error codes)

**Auth**: None  
**Frontend error handling**: Cache in memory/context; on failure use local defaults and optionally show "config load failed".

---

### 2.2 GET `/personas`

- **Method**: `GET`
- **Path**: `/personas`

**Request body**: None

**Response — Success (200)**  
```json
{
  "personas": {
    "Hands-on Explorer": { "description": "...", "fslsm_dimensions": { ... } },
    ...
  }
}
```

**Auth**: None  
**Frontend error handling**: On failure use built-in PERSONAS fallback (same as current Streamlit).

---

### 2.3 GET `/list-llm-models`

- **Method**: `GET`
- **Path**: `/list-llm-models`

**Request body**: None

**Response — Success (200)**  
```json
{ "models": [ { "model_name": "...", "model_provider": "..." } ] }
```

**Response — Error**: On `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: On failure return empty array and optionally show message.

---

## 3. User state

### 3.1 GET `/user-state/{user_id}`

- **Method**: `GET`
- **Path**: `/user-state/{user_id}`  
- **Path params**: `user_id`: string

**Request body**: None

**Response — Success (200)**  
```json
{ "state": { "goals": [...], "session_learning_times": {...}, "learned_skills_history": {...}, "document_caches": {...}, ... } }
```

**Response — Error**  
- `404`: `{"detail": "No state found for this user_id"}`

**Auth**: None (frontend may add JWT for user_id if required).  
**Frontend error handling**: Treat 404 as new user with empty state; retry once on network error.

---

### 3.2 PUT `/user-state/{user_id}`

- **Method**: `PUT`
- **Path**: `/user-state/{user_id}`  
- **Path params**: `user_id`: string

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `state` | object | ✅ | Full user state (goals, session_learning_times, etc.) |

Example: `{"state": { "goals": [], "session_learning_times": {} } }`

**Response — Success (200)**  
```json
{ "ok": true }
```

**Auth**: None  
**Frontend error handling**: On failure show "Save failed", allow retry; debounce/throttle to avoid overwrite conflicts.

---

### 3.3 DELETE `/user-state/{user_id}`

- **Method**: `DELETE`
- **Path**: `/user-state/{user_id}`  
- **Path params**: `user_id`: string

**Request body**: None

**Response — Success (200)**  
```json
{ "ok": true }
```

**Auth**: None
**Frontend error handling**: Show message on failure and optionally retry; often used with "clear data" actions.

---

### 3.4 DELETE `/user-data/{user_id}`

- **Method**: `DELETE`
- **Path**: `/user-data/{user_id}`
- **Path params**: `user_id`: string

**Request body**: None

**Response — Success (200)**
```json
{ "ok": true }
```

**Response — Error**
- `404`: `{"detail": "No state found for this user_id"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: On success clear all cached goals/sessions and redirect to `/onboarding`; on failure show error and allow retry. Use this for "restart onboarding" flows — it deletes goals and content caches but keeps the account.

---

## 4. Events

### 4.1 POST `/events/log`

- **Method**: `POST`
- **Path**: `/events/log`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `event_type` | string | ✅ | Event type |
| `payload` | object | optional | Default `{}` |
| `ts` | string (ISO) | optional | Server may fill |

Example: `{"user_id": "u1", "event_type": "session_start", "payload": {"goal_id": 1}}`

**Response — Success (200)**  
```json
{ "ok": true, "event_count": 42 }
```

**Auth**: None  
**Frontend error handling**: Fail silently or retry sparingly to avoid blocking; queue important events for retry.

---

## 5. Profile and sync

### 5.1 GET `/profile/{user_id}`

- **Method**: `GET`
- **Path**: `/profile/{user_id}?goal_id=<int>`  
- **Path params**: `user_id`: string  
- **Query**: `goal_id` (optional): number — if present returns that goal's profile, else all profiles for the user.

**Request body**: None

**Response — Success (200)**  
- With `goal_id`: `{"user_id": "...", "goal_id": 1, "learner_profile": { ... } }`
- Without `goal_id`: `{"user_id": "...", "profiles": [ { "goal_id": 1, "learner_profile": {...} }, ... ] }`

**Response — Error**  
- `404`: `{"detail": "No profile found for this user_id"}` or `"No profile found for this user_id and goal_id"`

**Auth**: None  
**Frontend error handling**: Treat 404 as no profile, guide to create; retry on network error.

---

### 5.2 PUT `/profile/{user_id}/{goal_id}`

- **Method**: `PUT`
- **Path**: `/profile/{user_id}/{goal_id}`  
- **Path params**: `user_id`: string, `goal_id`: number

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | object | ✅ | Learner profile object |

**Response — Success (200)**  
```json
{ "ok": true }
```

**Response — Error**  
- `400`: `{"detail": "learner_profile is required"}`

**Auth**: None  
**Frontend error handling**: 400 show invalid params; on network error show save failed and retry.

---

### 5.3 POST `/sync-profile/{user_id}/{goal_id}`

- **Method**: `POST`
- **Path**: `/sync-profile/{user_id}/{goal_id}`  
- **Path params**: `user_id`: string, `goal_id`: number

**Request body**: None

**Response — Success (200)**  
```json
{ "learner_profile": { ... } }
```

**Response — Error**  
- `404`: `{"detail": "No profile found for this goal"}`

**Auth**: None  
**Frontend error handling**: On 404 keep in-memory profile; on success update current goal with returned `learner_profile`.

---

### 5.4 POST `/profile/auto-update`

- **Method**: `POST`
- **Path**: `/profile/auto-update`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | optional | Default 0 |
| `model_provider` | string | optional | LLM provider |
| `model_name` | string | optional | Model name |
| `learning_goal` | string | conditional | Required when no profile |
| `learner_information` | any | conditional | Required when no profile |
| `skill_gaps` | any | conditional | Required when no profile |
| `session_information` | object | optional | Session metadata |

**Response — Success (200)**  
- Initialized: `{"ok": true, "mode": "initialized", "user_id": "...", "goal_id": 0, "event_count_used": 0, "learner_profile": {...}}`
- Updated: `{"ok": true, "mode": "updated", ...}`

**Response — Error**  
- `400`: `{"detail": "No profile found for this user_id. Provide learning_goal, learner_information, and skill_gaps to initialize."}`
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: 400 guide user to complete info; 500 show message and optionally retry.

---

## 6. Behavioral metrics and quizzes

### 6.1 GET `/behavioral-metrics/{user_id}`

- **Method**: `GET`
- **Path**: `/behavioral-metrics/{user_id}?goal_id=<int>`  
- **Path params**: `user_id`: string  
- **Query**: `goal_id` (optional): number

**Request body**: None

**Response — Success (200)**  
```json
{
  "user_id": "...",
  "goal_id": 1,
  "sessions_completed": 3,
  "total_sessions_in_path": 8,
  "sessions_learned": 2,
  "avg_session_duration_sec": 120.5,
  "total_learning_time_sec": 360.0,
  "motivational_triggers_count": 2,
  "mastery_history": [0.6, 0.8],
  "latest_mastery_rate": 0.8
}
```

**Response — Error**  
- `404`: `{"detail": "No state found for this user_id"}`

**Auth**: None  
**Frontend error handling**: 404 show empty or defaults; optionally retry on network error.

---

### 6.2 GET `/quiz-mix/{user_id}`

- **Method**: `GET`
- **Path**: `/quiz-mix/{user_id}?goal_id=<int>&session_index=<int>`  
- **Path params**: `user_id`: string  
- **Query**: `goal_id`: number, `session_index`: number

**Request body**: None

**Response — Success (200)**  
```json
{
  "single_choice_count": 3,
  "multiple_choice_count": 1,
  "true_false_count": 1,
  "short_answer_count": 1,
  "open_ended_count": 0
}
```

**Response — Error**  
- `400`: `{"detail": "Invalid session_index"}`  
- `404`: `{"detail": "No state found for this user_id"}` or `"Goal not found"`

**Auth**: None  
**Frontend error handling**: On failure use local default quiz mix (e.g. 3/1/1/1/0).

---

### 6.3 GET `/session-mastery-status/{user_id}`

- **Method**: `GET`
- **Path**: `/session-mastery-status/{user_id}?goal_id=<int>`  
- **Path params**: `user_id`: string  
- **Query**: `goal_id`: number

**Request body**: None

**Response — Success (200)**  
Array of: `{"session_id": "...", "is_mastered": false, "mastery_score": 65.0, "mastery_threshold": 70, "if_learned": false}`

**Response — Error**  
- `404`: `{"detail": "No state found for this user_id"}` or `"Goal not found"`

**Auth**: None  
**Frontend error handling**: 404 show empty list; retry on network error.

---

### 6.4 POST `/evaluate-mastery`

- **Method**: `POST`
- **Path**: `/evaluate-mastery`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | ✅ | Goal ID |
| `session_index` | number | ✅ | Session index |
| `quiz_answers` | object | ✅ | Keys include `single_choice_questions`, `multiple_choice_questions`, etc.; values are answer arrays |

**Response — Success (200)**  
```json
{
  "score_percentage": 75.0,
  "is_mastered": true,
  "threshold": 70,
  "correct_count": 6,
  "total_count": 8,
  "session_id": "Session 1",
  "plan_adaptation_suggested": false,
  "short_answer_feedback": [{ "is_correct": true, "feedback": "..." }],
  "open_ended_feedback": [{ "solo_level": "relational", "score": 0.8, "feedback": "..." }]
}
```

**Response — Error**  
- `400`: `{"detail": "Invalid session_index"}`  
- `404`: `{"detail": "No state found for this user_id"}` / `"Goal not found"` / `"No quiz data found for this session"}`

**Auth**: None  
**Frontend error handling**: Validate session and quiz loaded before submit; 404 show "Load content first"; retry once on 5xx.

---

## 7. Learning goal and skill gap (Onboarding / Skill Gap)

### 7.1 POST `/refine-learning-goal`

- **Method**: `POST`
- **Path**: `/refine-learning-goal`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learning_goal` | string | ✅ | Raw learning goal |
| `learner_information` | string | optional | Learner info (may be JSON string) |
| `model_provider` | string | optional | Same as BaseRequest |
| `model_name` | string | optional | Same as BaseRequest |
| `method_name` | string | optional | Default "genmentor" |

**Response — Success (200)**  
Backend may return a **string** (refined goal) or **object** depending on LLM. Frontend should accept both; if object, use `refined_goal` or top-level text field.

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Long timeout (LLM); show loading; on failure show message and allow retry.

---

### 7.2 POST `/identify-skill-gap-with-info`

- **Method**: `POST`
- **Path**: `/identify-skill-gap-with-info`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learning_goal` | string | ✅ | Learning goal |
| `learner_information` | string | ✅ | Learner info (may be JSON string) |
| `skill_requirements` | string | optional | Skill requirements (may be JSON) |
| `user_id` | string | optional | For storage if provided |
| `goal_id` | number | optional | Same |
| `model_provider` / `model_name` / `method_name` | Same as BaseRequest | optional | |

**Response — Success (200)**  
Object merging skill_gaps and skill_requirements (e.g. `skill_gaps`, `goal_assessment`, `retrieved_sources`; keys depend on backend).

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Long-running; show loading and timeout message; allow retry on failure.

---

### 7.3 POST `/audit-skill-gap-bias`

- **Method**: `POST`
- **Path**: `/audit-skill-gap-bias`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill_gaps` | string | ✅ | JSON-stringified skill_gaps object |
| `learner_information` | string | ✅ | Learner information |
| `model_provider` / `model_name` / `method_name` | Same as BaseRequest | optional | |

**Response — Success (200)**  
Audit result object (structure defined by backend).

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Show message on failure and optionally retry.

---

### 7.4 POST `/create-learner-profile-with-info`

- **Method**: `POST`
- **Path**: `/create-learner-profile-with-info`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learning_goal` | string | ✅ | Learning goal |
| `learner_information` | string | ✅ | Learner info (may be JSON string) |
| `skill_gaps` | string | ✅ | JSON-stringified skill_gaps (or `"[]"`) |
| `user_id` | string | optional | If provided, write to store |
| `goal_id` | number | optional | Same |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "learner_profile": { ... } }
```

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Show message and retry on failure; on success navigate to learning path or next step.

---

### 7.5 POST `/validate-profile-fairness`

- **Method**: `POST`
- **Path**: `/validate-profile-fairness`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | JSON-stringified profile |
| `learner_information` | string | ✅ | Learner information |
| `persona_name` | string | optional | Default "" |
| `model_provider` / `model_name` | optional |  | |

**Response — Success (200)**  
Fairness validation result object.

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Show message on failure; on success decide from result whether to allow next step.

---

## 8. Profile updates

### 8.1 POST `/update-learner-profile`

- **Method**: `POST`
- **Path**: `/update-learner-profile`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Current profile (may be JSON string) |
| `learner_interactions` | string | ✅ | Interaction log (may be JSON string) |
| `learner_information` | string | optional | Default "" |
| `session_information` | string | optional | Default "" |
| `user_id` / `goal_id` | string / number | optional | If provided, write to store |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "learner_profile": { ... } }
```

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Show message and retry on failure; on success update local state with returned `learner_profile`.

---

### 8.2 POST `/update-cognitive-status`

- **Method**: `POST`
- **Path**: `/update-cognitive-status`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Current profile |
| `session_information` | string | ✅ | Session info (may be JSON string) |
| `user_id` / `goal_id` | optional |  | |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "learner_profile": { ... } }
```

**Auth**: None  
**Frontend error handling**: May fail silently or show light message to avoid interrupting learning.

---

### 8.3 POST `/update-learning-preferences`

- **Method**: `POST`
- **Path**: `/update-learning-preferences`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Current profile |
| `learner_interactions` | string | ✅ | Interaction log |
| `learner_information` | string | optional | Default "" |
| `user_id` / `goal_id` | optional |  | |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "learner_profile": { ... } }
```

**Auth**: None
**Frontend error handling**: Same as 8.1.

---

### 8.4 POST `/update-learner-information`

- **Method**: `POST`
- **Path**: `/update-learner-information`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Current profile (JSON-stringified) |
| `updated_learner_information` | string | ✅ | New free-text learner information |
| `resume_text` | string | optional | Extracted PDF resume text to merge in |
| `user_id` | string | optional | If provided, write updated profile to store |
| `goal_id` | number | optional | Same |
| BaseRequest fields | optional | | |

**Response — Success (200)**
```json
{ "learner_profile": { ... } }
```

**Response — Error**
- `500`: `{"detail": "..."}`

**Auth**: None
**Frontend error handling**: On success update local goal state with returned `learner_profile`; show message and retry on failure.

---

## 9. Learning path

### 9.1 POST `/schedule-learning-path`

- **Method**: `POST`
- **Path**: `/schedule-learning-path`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile (may be JSON string) |
| `session_count` | number | ✅ | Session count |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
Object with `learning_path` (array) and optional `retrieved_sources`, etc.

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: Long-running (e.g. 500s timeout); show loading and timeout message; allow retry on failure.

---

### 9.2 POST `/reschedule-learning-path`

- **Method**: `POST`
- **Path**: `/reschedule-learning-path`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Current path (may be JSON string) |
| `session_count` | number | optional | Default -1 |
| `other_feedback` | string | optional | User feedback |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
Includes `rescheduled_learning_path`, etc. (structure defined by backend).

**Auth**: None  
**Frontend error handling**: Same as 9.1.

---

### 9.3 POST `/schedule-learning-path-agentic`

- **Method**: `POST`
- **Path**: `/schedule-learning-path-agentic`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile (may be JSON string) |
| `session_count` | number | optional | Default 0 |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
Includes `learning_path`, `agent_metadata`, etc.

**Auth**: None  
**Frontend error handling**: Recommend 120s timeout; allow retry on failure.

---

### 9.4 POST `/adapt-learning-path`

- **Method**: `POST`
- **Path**: `/adapt-learning-path`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | ✅ | Goal ID |
| `new_learner_profile` | string | ✅ | Updated profile (may be JSON string) |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
Includes `learning_path`, `agent_metadata` (e.g. decision, fslsm_deltas, evaluation_feedback).

**Response — Error**  
- `404`: No state or goal  
- `500`: `{"detail": "..."}`

**Auth**: None  
**Frontend error handling**: 404 prompt to load goal/state first; 500 show message and retry.

---

## 10. Knowledge content and quiz generation

### 10.1 POST `/explore-knowledge-points`

- **Method**: `POST`
- **Path**: `/explore-knowledge-points`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Learning path (may be JSON string) |
| `learning_session` | string | ✅ | Current session (may be JSON string) |

**Response — Success (200)**  
Includes `knowledge_points`, etc. (structure defined by backend).

**Auth**: None  
**Frontend error handling**: Show message and retry on failure.

---

### 10.2 POST `/draft-knowledge-point`

- **Method**: `POST`
- **Path**: `/draft-knowledge-point`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Path |
| `learning_session` | string | ✅ | Session |
| `knowledge_points` | string | ✅ | Knowledge points list (may be JSON string) |
| `knowledge_point` | string | ✅ | Current knowledge point |
| `use_search` | boolean | ✅ | Whether to use search |
| `model_provider` / `model_name` / `method_name` | optional |  | |

**Response — Success (200)**  
```json
{ "knowledge_draft": "..." }
```

**Auth**: None  
**Frontend error handling**: Show message and retry on failure.

---

### 10.3 POST `/draft-knowledge-points`

- **Method**: `POST`
- **Path**: `/draft-knowledge-points`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Path |
| `learning_session` | string | ✅ | Session |
| `knowledge_points` | string | ✅ | Knowledge points list |
| `allow_parallel` | boolean | ✅ | Allow parallel |
| `use_search` | boolean | ✅ | Use search |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "knowledge_drafts": [ ... ] }
```

**Auth**: None  
**Frontend error handling**: Same as 10.2.

---

### 10.4 POST `/integrate-learning-document`

- **Method**: `POST`
- **Path**: `/integrate-learning-document`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Path |
| `learning_session` | string | ✅ | Session |
| `knowledge_points` | string | ✅ | Knowledge points list |
| `knowledge_drafts` | string | ✅ | Draft content (may be JSON string) |
| `output_markdown` | boolean | optional | Default false |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{
  "learning_document": "<string or document_structure>",
  "content_format": "standard" | "visual_enhanced" | "podcast",
  "audio_url": "<url or null>",
  "document_is_markdown": false
}
```

**Auth**: None  
**Frontend error handling**: Show message and retry on failure; on success render content and audio per `content_format` / `audio_url`.

---

### 10.5 POST `/generate-document-quizzes`

- **Method**: `POST`
- **Path**: `/generate-document-quizzes`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_document` | string | ✅ | Learning document content |
| `single_choice_count` | number | optional | Default 3 |
| `multiple_choice_count` | number | optional | Default 0 |
| `true_false_count` | number | optional | Default 0 |
| `short_answer_count` | number | optional | Default 0 |
| `open_ended_count` | number | optional | Default 0 |

**Response — Success (200)**  
```json
{ "document_quiz": { "single_choice_questions": [...], "multiple_choice_questions": [...], "true_false_questions": [...], "short_answer_questions": [...], "open_ended_questions": [...] } }
```

**Auth**: None  
**Frontend error handling**: Show message and retry on failure.

---

### 10.6 POST `/tailor-knowledge-content`

- **Method**: `POST`
- **Path**: `/tailor-knowledge-content`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile |
| `learning_path` | string | ✅ | Path |
| `learning_session` | string | ✅ | Session |
| `use_search` | boolean | optional | Default true |
| `allow_parallel` | boolean | optional | Default true |
| `with_quiz` | boolean | optional | Default true |

**Response — Success (200)**  
```json
{ "tailored_content": { ... } }
```

**Auth**: None  
**Frontend error handling**: Show message and retry on failure.

---

### 10.7 POST `/simulate-content-feedback`

- **Method**: `POST`
- **Path**: `/simulate-content-feedback`

**Request body (JSON)**  
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | Profile (may be JSON string) |
| `learning_content` | string | ✅ | Learning content (may be JSON string) |
| BaseRequest fields | optional |  | |

**Response — Success (200)**  
```json
{ "feedback": { ... } }
```

**Auth**: None  
**Frontend error handling**: May fail silently or show light message (often used for internal evaluation).

---

## 11. Other

### 11.1 GET `/events/{user_id}`

- **Method**: `GET`
- **Path**: `/events/{user_id}`  
- **Path params**: `user_id`: string

**Response — Success (200)**  
```json
{ "user_id": "...", "events": [ ... ] }
```

**Auth**: None  
**Frontend error handling**: On failure return empty array or ignore.

---

### 11.2 POST `/extract-pdf-text`

- **Method**: `POST`
- **Path**: `/extract-pdf-text`  
- **Content-Type**: `multipart/form-data`

**Request body**: `file`: File (PDF)

**Response — Success (200)**  
```json
{ "text": "extracted raw text..." }
```

**Response — Error**  
- `500`: `{"detail": "..."}`

**Auth**: None
**Frontend error handling**: On failure show "PDF extraction failed" and allow re-upload.

---

## 12. Goals

### 12.1 GET `/goals/{user_id}`

- **Method**: `GET`
- **Path**: `/goals/{user_id}`
- **Path params**: `user_id`: string

**Request body**: None

**Response — Success (200)**
```json
{
  "goals": [
    {
      "id": 1,
      "learning_goal": "Learn Python for data science",
      "skill_gaps": { ... },
      "goal_assessment": { ... },
      "goal_context": { ... },
      "retrieved_sources": [...],
      "bias_audit": { ... },
      "profile_fairness": { ... },
      "learning_path": [...],
      "plan_agent_metadata": { ... },
      "learner_profile": { ... },
      "is_completed": false,
      "is_deleted": false
    }
  ]
}
```

**Response — Error**
- `404`: `{"detail": "No goals found for this user_id"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: 404 treat as empty list (new user with no goals); cache result in `GoalsContext`; invalidate on create/patch/delete.

---

### 12.2 POST `/goals/{user_id}`

- **Method**: `POST`
- **Path**: `/goals/{user_id}`
- **Path params**: `user_id`: string

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learning_goal` | string | ✅ | Learning goal text |
| `skill_gaps` | object | optional | Identified skill gap data |
| `goal_assessment` | object | optional | Goal assessment metadata |
| `goal_context` | object | optional | Contextual data for content generation |
| `retrieved_sources` | array | optional | Source references |
| `bias_audit` | object | optional | Bias audit result |
| `profile_fairness` | object | optional | Fairness validation result |
| `learner_profile` | object | optional | Learner profile at time of goal creation |
| `learning_path` | array | optional | Pre-populated learning path |
| `plan_agent_metadata` | object | optional | Scheduling agent metadata |

**Response — Success (200)**
Returns the created `GoalAggregate` object with server-assigned `id`.

**Response — Error**
- `500`: `{"detail": "..."}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: On success store the returned goal `id` and navigate to next step; on failure show error and allow retry.

---

### 12.3 PATCH `/goals/{user_id}/{goal_id}`

- **Method**: `PATCH`
- **Path**: `/goals/{user_id}/{goal_id}`
- **Path params**: `user_id`: string, `goal_id`: number

**Request body (JSON)**
Partial `GoalAggregate` — only include fields to update. Common updates:
| Field | Type | Description |
|-------|------|-------------|
| `learning_goal` | string | Revised goal text |
| `learning_path` | array | Updated session list (after scheduling or adaptation) |
| `plan_agent_metadata` | object | Scheduling agent metadata |

**Response — Success (200)**
Returns the full updated `GoalAggregate`.

**Response — Error**
- `404`: `{"detail": "Goal not found"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: On success update local goal cache in-place; on 404 show error.

---

### 12.4 DELETE `/goals/{user_id}/{goal_id}`

- **Method**: `DELETE`
- **Path**: `/goals/{user_id}/{goal_id}`
- **Path params**: `user_id`: string, `goal_id`: number

**Request body**: None

**Response — Success (200)**
```json
{ "ok": true }
```

**Response — Error**
- `404`: `{"detail": "Goal not found"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: On success remove from local goal list; ask for confirmation before calling; 404 treat as already deleted.

---

### 12.5 GET `/goal-runtime-state/{user_id}`

- **Method**: `GET`
- **Path**: `/goal-runtime-state/{user_id}?goal_id=<int>`
- **Path params**: `user_id`: string
- **Query**: `goal_id`: number — required

**Request body**: None

**Response — Success (200)**
```json
{
  "goal_id": 1,
  "adaptation": {
    "suggested": false,
    "message": "",
    "sources": []
  },
  "sessions": [
    {
      "session_index": 0,
      "session_id": "Session 1",
      "is_locked": false,
      "can_open": true,
      "can_complete": false,
      "completion_block_reason": null,
      "if_learned": false,
      "is_mastered": false,
      "mastery_score": null,
      "mastery_threshold": 70,
      "navigation_mode": "linear"
    }
  ]
}
```

**Response — Error**
- `404`: `{"detail": "Goal not found"}`

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: Used to drive lock/unlock/completion UI on Learning Path page. 404 show error; on `adaptation.suggested === true`, trigger `/adapt-learning-path` before rendering sessions.

---

## 13. Learning Content and Sessions

### 13.1 GET `/learning-content/{user_id}/{goal_id}/{session_index}`

- **Method**: `GET`
- **Path**: `/learning-content/{user_id}/{goal_id}/{session_index}`
- **Path params**: `user_id`: string, `goal_id`: number, `session_index`: number

**Request body**: None

**Response — Success (200)**
```json
{
  "document": "<markdown string or structured object>",
  "quizzes": {
    "single_choice_questions": [...],
    "multiple_choice_questions": [...],
    "true_false_questions": [...],
    "short_answer_questions": [...],
    "open_ended_questions": [...]
  },
  "content_format": "standard" | "audio_enhanced" | "visual_enhanced",
  "audio_url": "/static/audio/..." | null,
  "audio_mode": "podcast" | null,
  "view_model": {
    "sections": [
      { "title": "Introduction", "anchor": "intro", "level": 1, "markdown": "..." }
    ],
    "references": [
      { "index": 1, "label": "Some Source" }
    ]
  },
  "sources_used": [...]
}
```

**Response — Error**
- `404`: Content not yet generated for this session (expected — triggers generation flow)

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: **CRITICAL** — use `validateStatus: (s) => s < 500` so 404 resolves rather than throwing. Check response status in the page: 200 → render content; 404 → call `POST /generate-learning-content`. Do NOT show a toast on 404.

---

### 13.2 POST `/generate-learning-content`

- **Method**: `POST`
- **Path**: `/generate-learning-content`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `learner_profile` | string | ✅ | JSON-stringified `LearnerProfile` |
| `learning_path` | string | ✅ | JSON-stringified `LearningPathSession[]` |
| `learning_session` | string | ✅ | JSON-stringified specific `LearningPathSession` |
| `use_search` | boolean | optional | Default `true` |
| `allow_parallel` | boolean | optional | Default `true` |
| `with_quiz` | boolean | optional | Default `true` |
| `goal_context` | string | optional | JSON-stringified `goal_context` from `GoalAggregate` |
| `user_id` | string | optional | If provided, cache result by session key |
| `goal_id` | number | optional | Same |
| `session_index` | number | optional | Same |
| BaseRequest fields | optional | | |

**Response — Success (200)**
Same shape as `GET /learning-content` (section 13.1).

**Response — Error**
- `500`: `{"detail": "..."}`

**Auth**: None
**Frontend error handling**: **Use a 300-second AbortController timeout** — generation can take 3–5 minutes. Show "Generating personalized content…" spinner. On timeout or 5xx show message and "Regenerate" button. On success cache locally and render.

---

### 13.3 DELETE `/learning-content/{user_id}/{goal_id}/{session_index}`

- **Method**: `DELETE`
- **Path**: `/learning-content/{user_id}/{goal_id}/{session_index}`
- **Path params**: `user_id`: string, `goal_id`: number, `session_index`: number

**Request body**: None

**Response — Success (200)**
```json
{ "ok": true }
```

**Auth**: **JWT** — `Authorization: Bearer <token>`
**Frontend error handling**: Used by "Regenerate" button — delete cached content then re-trigger generation. On failure show error.

---

### 13.4 POST `/session-activity`

- **Method**: `POST`
- **Path**: `/session-activity`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | ✅ | Goal ID |
| `session_index` | number | ✅ | Session index (0-based) |
| `event_type` | string | ✅ | `"start"`, `"heartbeat"`, or `"end"` |

**Response — Success (200)**
```json
{
  "trigger": {
    "show": true,
    "message": "You've been learning for 30 minutes! Great work!"
  }
}
```
`trigger` is `null` or absent when no motivational trigger fires.

**Response — Error**
- `404`: `{"detail": "..."}`

**Auth**: None
**Frontend error handling**:
- Call with `event_type: "start"` before navigating to `/learning-session`
- Call with `event_type: "end"` on back/close
- Call with `event_type: "heartbeat"` on an interval (interval from `GET /config` → `motivational_trigger_interval_secs`, default 30s)
- On heartbeat response: if `trigger.show === true`, display `trigger.message` as a toast
- Fail silently for heartbeats; log errors for start/end

---

### 13.5 POST `/complete-session`

- **Method**: `POST`
- **Path**: `/complete-session`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | ✅ | Goal ID |
| `session_index` | number | ✅ | Session index |

**Response — Success (200)**
```json
{
  "goal": { /* full updated GoalAggregate */ }
}
```

**Response — Error**
- `400`: `{"detail": "Session cannot be completed yet"}` (completion gate not met)
- `404`: Goal or state not found

**Auth**: None
**Frontend error handling**: On success call `updateGoal(goalId, response.goal)` to replace the goal in-place (do NOT call `refreshGoals()` — avoids an extra round-trip). Button should be disabled when `GoalRuntimeState.sessions[index].can_complete === false`. For `navigation_mode: "linear"`, also gate on quiz mastery: disable if `!masteryResult?.is_mastered`.

---

### 13.6 POST `/submit-content-feedback`

- **Method**: `POST`
- **Path**: `/submit-content-feedback`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | ✅ | User ID |
| `goal_id` | number | ✅ | Goal ID |
| `feedback` | object | ✅ | Feedback payload (e.g. `{"clarity": 4, "relevance": 5, "depth": 3, "engagement": "high", "comments": "..."}`) |

Note: does **not** include `session_index`.

**Response — Success (200)**
```json
{
  "goal": { /* full updated GoalAggregate */ }
}
```

**Response — Error**
- `404`: Goal or state not found

**Auth**: None
**Frontend error handling**: On success call `updateGoal(goalId, response.goal)` in-place. Show confirmation toast; allow skipping (feedback is optional).

---

## 14. Dashboard Metrics

### 14.1 GET `/dashboard-metrics/{user_id}`

- **Method**: `GET`
- **Path**: `/dashboard-metrics/{user_id}?goal_id=<int>`
- **Path params**: `user_id`: string
- **Query**: `goal_id` (optional): number

**Request body**: None

**Response — Success (200)**
```json
{
  "user_id": "alice",
  "goal_id": 1,
  "overall_progress": 0.375,
  "skill_radar": {
    "labels": ["Python", "NumPy", "Pandas"],
    "current_levels": [2, 1, 0],
    "required_levels": [4, 3, 3]
  },
  "session_time_series": [
    { "session_index": 0, "duration_sec": 1800 },
    { "session_index": 1, "duration_sec": 2400 }
  ],
  "mastery_time_series": [
    { "session_index": 0, "mastery_pct": 72 },
    { "session_index": 1, "mastery_pct": 85 }
  ]
}
```

**Response — Error**
- `404`: `{"detail": "No state found for this user_id"}`

**Auth**: None
**Frontend error handling**: 404 treat as no data yet (show empty state); render charts only when respective arrays are non-empty. `overall_progress` is a 0–1 float; multiply by 100 for display.

---

## 15. Chat with Tutor

### 15.1 POST `/chat-with-tutor`

- **Method**: `POST`
- **Path**: `/chat-with-tutor`

**Request body (JSON)**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | string | ✅ | JSON-stringified message array: `[{"role": "user", "content": "..."}, ...]` |
| `learner_profile` | string | ✅ | JSON-stringified `LearnerProfile` |
| `user_id` | string | optional | User ID (for profile update persistence) |
| `goal_id` | number | optional | Active goal ID |
| `session_index` | number | optional | Current session index (for inline session chatbot) |
| `use_web_search` | boolean | optional | Default `false` |
| `use_vector_retrieval` | boolean | optional | Default `false` |
| `use_media_search` | boolean | optional | Default `false` |
| `allow_preference_updates` | boolean | optional | Default `true` |
| `return_metadata` | boolean | optional | Default `false` |
| `learner_information` | string | optional | Free-text learner background |
| BaseRequest fields | optional | | |

**Response — Success (200)**
```json
{
  "response": "Here's what I found about ...",
  "updated_learner_profile": { /* LearnerProfile or null */ }
}
```
`updated_learner_profile` is present only when the tutor detected a preference update worth persisting.

**Response — Error**
- `500`: `{"detail": "..."}`

**Auth**: None
**Frontend error handling**: Keep a rolling window of the last 20 messages to send (not the full history). On `updated_learner_profile` present, call `updateGoal(goalId, { ...activeGoal, learner_profile: updated })` in-place. Show streaming-like typing indicator while pending. On failure show error in chat bubble and allow retry.

---

## Auth and token summary

| Endpoint type | Auth | Token storage |
|---------------|------|----------------|
| `/auth/register`, `/auth/login` | None | After success store `token` in `localStorage.auth_token` (or sessionStorage) and in memory (Context/Store) |
| `/auth/me`, `/auth/user` (DELETE) | JWT | Header `Authorization: Bearer <token>`; read token from same store |
| Other endpoints | None (current) | If adding per-user auth later, attach JWT in axios/fetch interceptor |

**Frontend error handling summary**  
- **401** (auth only): Clear token and **redirect to login**.  
- **404**: Handle by endpoint semantics (e.g. init or show empty when state/profile missing).  
- **4xx**: Show `detail`; do not retry or retry only idempotent operations.  
- **5xx / network**: Retry **once** for critical calls (e.g. state save, path generation, quiz submit); then show "Service temporarily unavailable. Please try again later."  
- **Long-running** (e.g. schedule-learning-path, identify-skill-gap, LLM): **Loading + reasonable timeout** (e.g. 120–500s); after timeout show message and allow retry.
