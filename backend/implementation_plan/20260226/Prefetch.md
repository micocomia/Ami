## V3 Plan: Backend-Owned Prefetch With Single-Flight Join

### Summary
Implement server-side prefetch so session content is ready at click time, without adding frontend orchestration.  
Core guarantees:
1. No duplicate generation for the same `(user_id, goal_id, session_index)`.
2. Click-during-prefetch joins existing work.
3. Stale prefetch results are never written after plan changes.
4. Frontend stays unchanged/light (React-friendly).

### Scope
- In scope: backend triggering, inflight coordination, cache invalidation, join/wait behavior, tests.
- Out of scope: frontend workflow changes, queue infra (Redis/Celery), multi-process distributed locking.

### Public Interfaces
1. Keep existing frontend APIs unchanged:
- `GET /learning-content/{user_id}/{goal_id}/{session_index}`
- `POST /generate-learning-content`
- `PATCH /goals/{user_id}/{goal_id}`
- `POST /adapt-learning-path`
- `POST /session-activity`

2. Optional API addition (recommended):
- `GET /learning-content/...` optional query: `no_wait=true` (diagnostic only).
- Default remains wait-if-inflight; UI will not pass flags.

### Config Additions
Add to backend config (`/backend/config/default.yaml` and surfaced in `/config`):
- `prefetch_enabled: true`
- `prefetch_wait_short_secs: 8` (for `GET /learning-content`)
- `prefetch_wait_long_secs: 130` (for `POST /generate-learning-content` join)
- `prefetch_cooldown_secs: 20`
- `prefetch_max_workers: 2`

### Internal Backend Changes

#### 1) Single-flight registry
In `/backend/main.py`, add process-local registry keyed by `"{user}:{goal}:{session}"` with lock:
- `status`: `running|succeeded|failed|discarded`
- `event`: `threading.Event`
- `owner_token`: unique id for the active run
- `path_hash_at_start`
- `started_at`, `finished_at`, `error`
- `trigger_source`

Rules:
- Only one active owner per key.
- Joiners wait on `event`; they never become owner while `status=running`.
- Owner always resolves state and sets `event` in `finally`.

#### 2) Candidate selection
- Trigger `goal_patch`/`adapt_applied`: first unlearned session in current path.
- Trigger `session_start`: first unlearned session strictly after `current_session_index`.
- If no candidate: noop.

#### 3) Trigger wiring (backend-owned)
1. `PATCH /goals/{user}/{goal}`:
- Only trigger when payload includes `learning_path`.
- Compare old/new path hash; enqueue only if changed.

2. `POST /adapt-learning-path`:
- On `adaptation.status == "applied"`:
  - invalidate stale caches in changed future portion
  - enqueue prefetch for first unlearned session.

3. `POST /session-activity` with `event_type=start`:
- enqueue next-session prefetch (dedupe + cooldown + cache checks).

#### 4) Cache invalidation policy
Use “Invalidate Changed” with precision:
- Compute future sessions (unlearned) before vs after adaptation.
- Delete cache only for indices where session identity/structure changed.
- Preserve unchanged future session cache.

#### 5) Stale-write protection
Owner stores `path_hash_at_start`; before writing cache:
- Recompute current path hash.
- If mismatch: mark `discarded`, skip write.

#### 6) Read/generate behavior
1. `GET /learning-content`:
- Return cache if present.
- If miss and inflight running: wait `prefetch_wait_short_secs`, re-check cache.
- If still miss: return 404 (existing fallback path preserved).

2. `POST /generate-learning-content`:
- Return cache if present.
- If inflight running for same key: wait `prefetch_wait_long_secs`, re-check cache.
- Only if still missing (failed/timeout/discard/no inflight), become owner and generate synchronously.
- This is the only path allowed to start fallback generation.

### Files To Update
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/config/default.yaml`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/api_schemas.py` (only if adding optional query/schema helpers)
- No required frontend file changes.

### Test Plan

#### New tests
Add `/backend/tests/test_learning_content_prefetch.py`:
1. `patch_goal` with changed learning_path enqueues single prefetch.
2. `patch_goal` without learning_path change does not prefetch.
3. `session start` enqueues next session only.
4. Existing cache skips enqueue.
5. Duplicate trigger while inflight does not create second owner.
6. `GET /learning-content` joins short wait and returns cache when prefetch completes.
7. `POST /generate-learning-content` joins long wait and does not duplicate generation.
8. Path hash change during prefetch marks run discarded and prevents stale write.
9. Adaptation-applied invalidates only changed future sessions.
10. Cooldown prevents rapid repeat enqueue flood.

#### Existing test touchpoints
Extend:
- `/backend/tests/test_goal_resources.py` for endpoint behavior with inflight wait.
- `/backend/tests/test_onboarding_api.py` adaptation flow with prefetch side effects.

### Rollout
1. Ship behind `prefetch_enabled`.
2. Enable in dev, verify logs/latency.
3. Run backend test suite.
4. Enable in staging.
5. Monitor:
- cache hit rate on first click
- duplicate generation count (should trend to near-zero)
- average click-to-content latency

### Assumptions and Defaults
- Single-process backend runtime (current JSON-store architecture).
- Quality unchanged: prefetch uses existing `generate_learning_content_with_llm` pipeline.
- Frontend remains passive and unchanged; all orchestration lives in backend.
