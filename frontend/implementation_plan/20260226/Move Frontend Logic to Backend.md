# Complete `/user-state` Removal and Streamlit Thinning Plan

## Summary
This plan replaces the generic `/user-state` blob with explicit backend resources, removes nonessential Streamlit ecosystem dependencies, and keeps Streamlit working as a thin functional client while React becomes the richer presentation client.

This revision fixes the main gaps in the earlier plan:

- deleting `/user-state` requires a real backend goal resource model
- deleting `/user-state` requires a backend learning-content cache, because `/evaluate-mastery` currently depends on `document_caches` inside user state
- deleting `/user-state` requires backend-owned session activity and mastery-history storage, because analytics currently read `session_learning_times`, `learned_skills_history`, and `goals` from user state
- deleting `/user-state` requires removing many `save_persistent_state()` flows from Streamlit pages
- package cleanup must cover not just dead components, but `frontend/requirements.txt` entries for Streamlit ecosystem packages that are no longer imported anywhere

This is a compatibility-first migration:
- first add explicit backend resources
- then migrate Streamlit to those resources
- then remove `/user-state`
- then remove dead Streamlit-only dependencies and modules

## End-State Design
Backend owns:
- goal records
- learner profiles
- learning paths
- generated content cache
- quiz/mastery results
- session activity timing
- dashboard analytics inputs and outputs
- runtime state and lock/completion decisions
- profile propagation across goals

Streamlit owns only:
- widget state
- current page/tab/section
- unsaved form values
- immediate UI toggles/debug flags
- local navigation

React will also own only client/UI state. It will not have a backend `/user-state` equivalent.

## Important Decision
`/user-state` is deleted completely in the end state.

What replaces it:
- explicit goal endpoints
- explicit learning-content cache endpoints
- explicit session activity endpoints
- explicit runtime-state endpoints
- explicit dashboard metrics endpoints

What does not get replaced:
- UI-only draft state like selected tab/page or open dialog
- those become client-local only in both Streamlit and React

## Critical Gaps and Bugs Found

### 1. Current goal data is not stored anywhere except frontend state and `/user-state`
Current issue:
- `goals` are created and managed in Streamlit state
- backend stores profiles separately, but not the goal aggregate used by the frontend
- goal management, learning path display, and selected-goal logic depend on `st.session_state["goals"]`

Fix:
- add backend goal resources and make them authoritative

### 2. `/evaluate-mastery` currently depends on `document_caches` inside `/user-state`
Current issue:
- `/evaluate-mastery` loads quizzes from `state["document_caches"][session_uid]["quizzes"]`
- if `/user-state` is deleted without replacing this cache, quiz evaluation breaks immediately

Fix:
- persist generated learning content server-side by `user_id + goal_id + session_index`
- change `/evaluate-mastery` to read quiz payload from that server-side cache

### 3. Behavioral metrics currently depend on `/user-state`
Current issue:
- `GET /behavioral-metrics/{user_id}` reads:
  - `session_learning_times`
  - `learned_skills_history`
  - `goals`
- all of those currently live in `/user-state`

Fix:
- add explicit backend stores for session activity and mastery history
- compute metrics from those stores instead of `/user-state`

### 4. Streamlit `main.py` samples mastery history locally
Current issue:
- [frontend/main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/main.py) writes `goal["start_time"]` and appends mastery samples every 10 minutes
- this is domain logic disguised as app-shell code

Fix:
- move mastery-history sampling to the backend activity/analytics layer
- remove this logic from Streamlit completely

### 5. Cross-goal propagation currently happens in the frontend
Current issue:
- [propagate_profile_fields_to_other_goals()](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/state.py) mutates other goals and persists them from the client

Fix:
- move propagation fully to the backend
- clients should receive already-synced profiles/goal aggregates

## Backend Resource Model To Add

## 1. Goal Resource
Add backend storage for goals.

### Store
Add a new persisted store, either:
- `backend/utils/store.py` extended with a `_goals` map and `goals.json`
- or a dedicated `goal_store.py`

Decision:
- extend `backend/utils/store.py` for consistency with the current persistence approach

### Goal record shape
```json
{
  "id": 3,
  "user_id": "alice",
  "learning_goal": "Learn introductory Python",
  "skill_gaps": [],
  "goal_assessment": {},
  "goal_context": {},
  "retrieved_sources": [],
  "bias_audit": null,
  "profile_fairness": null,
  "learning_path": [],
  "is_completed": false,
  "is_deleted": false,
  "created_at": "2026-02-27T12:00:00Z",
  "updated_at": "2026-02-27T12:00:00Z"
}
```

### Goal aggregate response shape
When goals are fetched, backend joins the goal record with the existing stored learner profile:
```json
{
  "id": 3,
  "learning_goal": "...",
  "skill_gaps": [],
  "goal_assessment": {},
  "goal_context": {},
  "retrieved_sources": [],
  "bias_audit": null,
  "profile_fairness": null,
  "learning_path": [],
  "is_completed": false,
  "is_deleted": false,
  "learner_profile": {}
}
```

### Endpoints
#### `GET /goals/{user_id}`
Returns all non-deleted goal aggregates for the user.

#### `POST /goals/{user_id}`
Creates a goal.
Request:
```json
{
  "learning_goal": "...",
  "skill_gaps": [],
  "goal_assessment": {},
  "goal_context": {},
  "retrieved_sources": [],
  "bias_audit": null,
  "profile_fairness": null,
  "learning_path": [],
  "learner_profile": {}
}
```

Response:
- created goal aggregate

#### `PATCH /goals/{user_id}/{goal_id}`
Updates goal metadata and/or learning path.
Allowed fields:
- `learning_goal`
- `skill_gaps`
- `goal_assessment`
- `goal_context`
- `retrieved_sources`
- `bias_audit`
- `profile_fairness`
- `learning_path`
- `is_completed`
- `is_deleted`

#### `DELETE /goals/{user_id}/{goal_id}`
Soft-delete the goal.
Behavior:
- set `is_deleted = true`
- do not physically delete profile/content/activity immediately

### Notes
- There is no backend “selected_goal_id”.
- selected goal remains client-local in Streamlit and React.

## 2. Learning Content Cache Resource
Add backend storage for generated content.

### Store
Add persisted `learning_content.json` keyed by:
- `{user_id}:{goal_id}:{session_index}`

### Cache record shape
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "session_index": 1,
  "learning_content": {
    "document": "...",
    "quizzes": {},
    "sources_used": [],
    "content_format": "standard",
    "audio_url": "/static/audio/abc.mp3",
    "audio_mode": "narration_optional",
    "inline_assets_count": 0,
    "inline_assets_placement_stats": {},
    "view_model": {}
  },
  "created_at": "2026-02-27T12:00:00Z",
  "updated_at": "2026-02-27T12:00:00Z"
}
```

### Endpoint changes
#### Extend `POST /generate-learning-content`
Add optional request fields:
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "session_index": 1
}
```

Behavior:
- if all three are present, persist the generated content to the cache store
- response payload remains the flat learning content object

#### `GET /learning-content/{user_id}/{goal_id}/{session_index}`
Returns the cached learning content if present.
Response:
- same learning content payload as `/generate-learning-content`

#### `DELETE /learning-content/{user_id}/{goal_id}/{session_index}`
Invalidates cached content for regenerate flows.

### Why this is required
This is the replacement for `document_caches` in `/user-state`.

## 3. Session Activity Resource
Add backend activity tracking to replace `session_learning_times`.

### Store
Add `session_activity.json` keyed by:
- `{user_id}:{goal_id}:{session_index}`

### Record shape
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "session_index": 1,
  "start_time": "2026-02-27T12:00:00Z",
  "end_time": null,
  "heartbeats": ["2026-02-27T12:05:00Z"],
  "trigger_events": [
    {"kind": "posture", "time": "2026-02-27T12:10:00Z"}
  ]
}
```

### Endpoint
#### `POST /session-activity`
Request:
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "session_index": 1,
  "event_type": "start",
  "event_time": "2026-02-27T12:00:00Z"
}
```

Allowed `event_type`:
- `start`
- `heartbeat`
- `end`

Response:
```json
{
  "ok": true,
  "trigger": {
    "show": true,
    "kind": "posture",
    "message": "Stay hydrated and keep a healthy posture."
  }
}
```

Behavior:
- `start`: initialize session activity if absent
- `heartbeat`: append heartbeat if spaced enough from prior heartbeat
- `end`: set end time if unset
- compute trigger cadence backend-side from `motivational_trigger_interval_secs`

## 4. Mastery History Resource
Add backend mastery-history storage to replace `learned_skills_history` in `/user-state`.

### Store
Add `mastery_history.json` keyed by:
- `{user_id}:{goal_id}` -> list of samples

### Sample shape
```json
{
  "sample_time": "2026-02-27T12:00:00Z",
  "mastery_rate": 0.42
}
```

### Update behavior
- update after:
  - successful `POST /complete-session`
  - successful `POST /evaluate-mastery`
  - successful profile sync if mastered skills changed
- no frontend sampling loop

## 5. Runtime State Resource
Add the runtime-state endpoint from the earlier plan.

### `GET /goal-runtime-state/{user_id}?goal_id=<id>`
Response:
```json
{
  "goal_id": 3,
  "adaptation": {
    "suggested": false,
    "message": null
  },
  "sessions": [
    {
      "session_index": 0,
      "session_id": "Session 1",
      "is_locked": false,
      "can_open": true,
      "can_complete": true,
      "completion_block_reason": null,
      "if_learned": true,
      "is_mastered": true,
      "mastery_score": 82.0,
      "mastery_threshold": 70,
      "navigation_mode": "linear"
    }
  ]
}
```

Behavior:
- compute lock rules server-side
- compute completion eligibility server-side
- expose adaptation suggestion state server-side

## 6. Consolidated Action Endpoints
### `POST /complete-session`
Request:
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "session_index": 1,
  "session_end_time": "2026-02-27T12:30:00Z"
}
```

Behavior:
- mark session learned in goal store
- end session activity
- update cognitive status
- persist learner profile
- apply cross-goal profile merge
- append mastery-history sample
- return updated goal aggregate and runtime state

Response:
```json
{
  "ok": true,
  "goal": {},
  "learner_profile": {},
  "updated_session": {},
  "goal_runtime_state": {},
  "profile_sync_applied": true
}
```

### `POST /submit-content-feedback`
Request:
```json
{
  "user_id": "alice",
  "goal_id": 3,
  "feedback": {
    "clarity": 4,
    "relevance": 5,
    "depth": 4,
    "engagement": 3,
    "additional_comments": "Useful examples."
  }
}
```

Behavior:
- update learning preferences
- persist learner profile
- apply cross-goal profile merge
- return updated goal aggregate and runtime state

## 7. Dashboard Metrics Resource
Add:
### `GET /dashboard-metrics/{user_id}?goal_id=<id>`
Response:
```json
{
  "goal_id": 3,
  "overall_progress": 42.5,
  "skill_radar": {
    "labels": ["Python", "Functions"],
    "current_levels": [2, 1],
    "required_levels": [3, 2],
    "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"]
  },
  "session_time_series": [
    {"session_id": "Session 1", "time_spent_min": 22.5}
  ],
  "mastery_time_series": [
    {"sample_index": 0, "mastery_rate": 0.15}
  ],
  "behavioral_metrics": {
    "sessions_completed": 2,
    "total_learning_time_sec": 3100.0,
    "motivational_triggers_count": 4,
    "latest_mastery_rate": 0.42
  }
}
```

Behavior:
- compute from goal store + session activity + mastery history
- replace dashboard recomputation in Streamlit

## Required Revisions to Existing Endpoints

## 1. Revise `POST /evaluate-mastery`
Current bug:
- reads quizzes from `state["document_caches"]`

Required change:
- read quizzes from learning-content cache:
  - key: `{user_id}:{goal_id}:{session_index}`
- never read `/user-state`

Additional behavior:
- update goal learning path mastery fields in goal store
- append mastery-history sample
- response stays backward-compatible

## 2. Revise `GET /behavioral-metrics/{user_id}`
Current bug:
- reads `goals`, `session_learning_times`, `learned_skills_history` from `/user-state`

Required change:
- read from:
  - goal store
  - session activity store
  - mastery history store

Keep endpoint response shape unchanged for compatibility.

## 3. Revise `GET /session-mastery-status/{user_id}`
Current bug:
- reads goal path from `/user-state`

Required change:
- read from goal store

## 4. Revise `POST /adapt-learning-path`
Current bug:
- reads user goal state from `/user-state`

Required change:
- read from goal store
- persist adapted path to goal store

## `/user-state` Deletion Strategy

## Phase 1: Dual-write compatibility
Keep `/user-state` temporarily, but:
- add goal store
- add learning-content cache store
- add session activity store
- add mastery history store
- update backend flows to write explicit stores
- Streamlit still works without change during this phase

## Phase 2: Streamlit read migration
Rewire Streamlit to stop reading `/user-state` for domain logic:
- goals from `GET /goals/{user_id}`
- runtime state from `GET /goal-runtime-state`
- content cache from `GET /learning-content/...`
- dashboard from `GET /dashboard-metrics`
- activity via `POST /session-activity`

## Phase 3: Streamlit write migration
Remove `save_persistent_state()` / `load_persistent_state()` use for domain state:
- no more saving `goals`
- no more saving `document_caches`
- no more saving `session_learning_times`
- no more saving `mastery_status`
- no more saving `learned_skills_history`

Only retain local `st.session_state` for UI/transient concerns.

## Phase 4: Delete `/user-state`
Delete endpoints from [backend/main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py):
- `GET /user-state/{user_id}`
- `PUT /user-state/{user_id}`
- `DELETE /user-state/{user_id}`

Delete corresponding store methods from [backend/utils/store.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/utils/store.py):
- `get_user_state`
- `put_user_state`
- `delete_user_state`
- `_USER_STATES_PATH`
- `_user_states`
- `_flush_user_states`

Delete tests:
- [backend/tests/test_user_state.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/tests/test_user_state.py)

Update tests that still seed state using `store.put_user_state(...)`:
- auth tests
- behavioral metrics tests
- mastery/session status tests

## Streamlit Code To Revise or Delete

## Delete immediately
These are dead or not needed.

### Files
- [frontend/components/navigation.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/components/navigation.py)
- [frontend/components/session_completion.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/components/session_completion.py)
- [frontend/utils/backend.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/backend.py)

### Imports
Remove unused imports:
- `render_navigation` from:
  - [frontend/pages/learning_path.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/learning_path.py)
  - [frontend/pages/learner_profile.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/learner_profile.py)
- `tagger_component` from:
  - [frontend/pages/learner_profile.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/learner_profile.py)

### Functions
Delete immediately:
- [prepare_markdown_document()](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/format.py)
- [convert_knowledge_perspectives_to_markdown()](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/format.py)

## Revise now, delete later

### `frontend/utils/state.py`
Revise to keep only:
- initialization of UI defaults
- `get_selected_goal()` and goal-selection helpers that operate on already-fetched goal lists
- `get_current_session_uid()`
- UI-only local session helpers

Delete after migration:
- `load_persistent_state`
- `save_persistent_state`
- `delete_persistent_state`
- `propagate_profile_fields_to_other_goals`
- all `PERSIST_KEYS` entries tied to domain persistence
- all backend persistence debouncing logic

### `frontend/main.py`
Delete business logic:
- periodic mastery sampling
- writing `goal["start_time"]`
- any domain-state persistence writes

Keep:
- page registration
- debug sidebar
- auth gating
- UI-only toggles

### `frontend/pages/goal_management.py`
Revise:
- stop using local `goals` as the source of truth
- fetch goals from backend
- create/update/delete goals via goal resource endpoints

Keep local-only:
- `to_add_goal` draft while the user is still editing
- draft does not persist to backend across refresh

### `frontend/pages/skill_gap.py`
Revise:
- keep `to_add_goal` as local draft only
- on “Schedule Learning Path”, create goal via backend goal endpoint instead of `add_new_goal(...)`

### `frontend/pages/knowledge_document.py`
Revise:
- generate content with `user_id`, `goal_id`, `session_index` so it persists server-side
- fetch cached content via backend if already present
- render `view_model.sections`
- complete session via `POST /complete-session`
- send activity heartbeats via `POST /session-activity`
- send feedback via `POST /submit-content-feedback`
- stop using local `document_caches`, `session_learning_times`, and `mastery_status` as canonical state

Delete later:
- `render_motivational_triggers`
- `update_learner_profile_with_feedback`
- markdown splitting / TOC reconstruction / reference extraction logic
- asset URL absolutization logic
- citation tooltip injection if backend returns ready-to-render section content

### `frontend/pages/learning_path.py`
Revise:
- fetch goals from backend
- fetch runtime state from backend
- use runtime state instead of `_is_session_locked()`
- use backend adaptation state instead of local flags

Delete later:
- `_is_session_locked`
- adaptation flag logic tied to `st.session_state[f"adaptation_suggested_{goal_id}"]`

### `frontend/pages/dashboard.py`
Revise:
- use `GET /dashboard-metrics`
- do not read local `session_learning_times` or `learned_skills_history`

## Streamlit Ecosystem Dependency Cleanup

## Keep
- `streamlit`
- `streamlit-float`
  - only used by [frontend/components/chatbot.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/components/chatbot.py)
  - presentation-only, acceptable to keep

## Remove after code cleanup
These packages are confirmed unnecessary from current source import scan.

### Remove from `frontend/requirements.txt`
- `streamlit-option-menu`
- `streamlit-extras`

Reason:
- `streamlit-option-menu` is only used in dead `components/navigation.py`
- `streamlit-extras` only appears via unused `tagger_component` import

## Remove after a requirements prune pass
These packages have no live source imports in `frontend/` based on the current scan and should be removed unless another runtime entrypoint outside the repo uses them:
- `altex`
- `extra-streamlit-components`
- `markdownlit`
- `st-annotated-text`
- `st-pages`
- `st-theme`
- `streamlit-avatar`
- `streamlit-camera-input-live`
- `streamlit-card`
- `streamlit-chat`
- `streamlit-embedcode`
- `streamlit-image-coordinates`
- `streamlit-keyup`
- `streamlit-notify`
- `streamlit-on-Hover-tabs`
- `streamlit-tags`
- `streamlit-toggle-switch`
- `streamlit-vertical-slider`
- `streamlit_faker`

### Safety rule for dependency pruning
- remove only packages with zero live imports under `frontend/`
- run import smoke tests after each removal batch
- do not remove `streamlit-float`
- do not remove core `streamlit`

## Request API Contract Additions

Add wrappers in [frontend/utils/request_api.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/request_api.py):

- `list_goals(user_id)`
- `create_goal(user_id, goal_payload)`
- `update_goal(user_id, goal_id, patch_payload)`
- `delete_goal(user_id, goal_id)`
- `get_goal_runtime_state(user_id, goal_id)`
- `get_learning_content(user_id, goal_id, session_index)`
- `complete_session(user_id, goal_id, session_index, session_end_time=None)`
- `submit_content_feedback(user_id, goal_id, feedback)`
- `post_session_activity(user_id, goal_id, session_index, event_type, event_time=None)`
- `get_dashboard_metrics(user_id, goal_id)`

Revise:
- `generate_learning_content(...)` to accept optional `user_id`, `goal_id`, `session_index`
- remove:
  - `get_user_state`
  - `save_user_state`
  - `delete_user_state`

## Tests and Scenarios

## Backend tests to add/update
1. Goal resource tests
   - create goal
   - list goals
   - patch goal
   - soft-delete goal
   - list returns assembled goal aggregates with learner profile

2. Learning content cache tests
   - `/generate-learning-content` persists when ids are provided
   - `/learning-content/{user_id}/{goal_id}/{session_index}` returns cached content
   - delete cache invalidates regenerate path

3. Mastery evaluation tests
   - `/evaluate-mastery` reads quizzes from learning-content cache, not `/user-state`
   - failure when no cached content exists is explicit and correct

4. Behavioral metrics tests
   - compute from session activity + mastery history + goal store
   - no dependency on `/user-state`

5. Runtime state tests
   - lock rule correctness
   - completion gating correctness
   - adaptation suggestion correctness

6. Complete-session tests
   - session marked learned
   - profile updated
   - cross-goal sync applied
   - mastery-history sample added
   - session activity ended if open

7. Dashboard metrics tests
   - chart-ready payload
   - stable when no activity exists
   - stable when no mastery history exists

8. Deletion tests
   - `/user-state/*` endpoints return 404 after final migration phase
   - old user-state tests removed and replaced by goal/content/activity resource tests

## Frontend compatibility tests
1. Streamlit onboarding works without `/user-state`
2. Streamlit goal management works from backend goals
3. Streamlit content page works using cached or generated content from backend
4. Streamlit mastery flow works without local `document_caches`
5. Streamlit dashboard works without local `session_learning_times` or `learned_skills_history`
6. Streamlit survives refresh with backend-fetched domain state
7. Streamlit loses only UI draft state on refresh, not domain state

## Acceptance Criteria
1. `/user-state` is fully deleted.
2. No backend endpoint reads or writes generic user-state blobs.
3. Streamlit remains functional using explicit backend resources.
4. React can implement the full product flow without any `/user-state` equivalent.
5. `/evaluate-mastery` no longer depends on frontend-persisted caches.
6. Dashboard metrics are backend-owned.
7. Cross-goal profile sync is backend-owned.
8. Unused Streamlit ecosystem packages are removed from `frontend/requirements.txt`.

## Assumptions and Defaults
- UI-only draft state such as `to_add_goal` no longer persists across browser refresh.
- selected goal, selected session, open page, and debug flags remain client-local only.
- profiles continue to be stored in the existing profile store and are joined into goal aggregates on read.
- the backend learning-content cache is the canonical source for quiz payload retrieval during mastery evaluation.
- goal deletion is soft-delete in this pass.
- Streamlit remains a maintained reference client, not a temporary migration-only client.
- React is expected to consume the same backend resources without special-case endpoints.

## Exact Bug/Risk Checklist Addressed by This Plan
- `/evaluate-mastery` cache dependency bug: fixed by learning-content cache
- behavioral metrics dependence on `/user-state`: fixed by explicit activity/history stores
- goal management reliance on frontend-only goal list: fixed by goal resource
- cross-goal sync living in frontend: fixed by backend orchestration
- app-shell mastery sampling bug/risk: fixed by backend mastery-history updates
- dead Streamlit component imports: explicitly removed
- unnecessary Streamlit package sprawl: explicitly pruned
