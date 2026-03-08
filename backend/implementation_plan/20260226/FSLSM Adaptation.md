## Tightened Plan v2: Backend-First Band-Triggered Auto-Adaptation via Existing `/adapt-learning-path`

### Summary
Implement seamless learning-path adaptation with backend-owned logic, using static FSLSM bands and conservative performance-driven updates, while removing manual rescheduling/adaptation UI. This version closes gaps around drift, idempotency stability, concurrency, snapshot lifecycle, and schema completeness.

### Locked Policy
1. Reuse and extend `POST /adapt-learning-path` (no new endpoint).
2. Remove public/manual `POST /reschedule-learning-path` and frontend re-schedule UI.
3. FSLSM trigger points are fixed bands: `-0.7, -0.3, 0.3, 0.7`.
4. Band transitions use hysteresis `±0.02`.
5. FSLSM vectors are overwritten in learner profile (chosen policy).
6. Failure-driven updates are conservative and scoped to session-signaled dimensions.
7. Add explicit session `input_mode_hint` field for deterministic `fslsm_input` handling.

## End-to-End Behavior

### A) Adaptation trigger model (backend-owned)
Adaptation is triggered when any effective FSLSM dimension crosses a band boundary (with hysteresis), not by raw delta magnitude.

Band labels:
- `strong_negative <= -0.7`
- `mild_negative (-0.7, -0.3]`
- `neutral (-0.3, 0.3)`
- `mild_positive [0.3, 0.7)`
- `strong_positive >= 0.7`

Hysteresis thresholds:
- strong+/mild+ boundary: enter `>=0.72`, exit `<0.68`
- mild+/neutral boundary: enter `>=0.32`, exit `<0.28`
- neutral/mild- boundary: enter `<=-0.32`, exit `>-0.28`
- mild-/strong- boundary: enter `<=-0.72`, exit `>-0.68`

### B) Quiz-performance FSLSM update model (across path, by key)
Evidence is tracked across the learning path by key: `(dimension, sign)`.

Severe failure definition:
- `not is_mastered` and `score < threshold * 0.8` (same as current intent)

Penalty trigger (conservative):
- if a key has `>=3` recent observations and `2 severe failures in last 3`, then:
  - failing positive-style key: decrement dim by `0.10`
  - failing negative-style key: increment dim by `0.10`
- clamp FSLSM to `[-1.0, +1.0]`

Recovery rule (added to prevent one-way drift):
- if a key has `>=3` recent observations and `2 strong successes in last 3`
  - strong success: mastered with margin (`score >= threshold + 10`)
  - apply rebound `0.05` toward neutral (`0`) for that signaled direction
- same daily movement cap applies.

Daily cap:
- max absolute movement per dimension per goal per 24h: `0.20`.

### C) Session-signaled dimension mapping
Use explicit session fields only (no fuzzy inference except fallback):

- `processing`
  - `has_checkpoint_challenges=true` => negative-style signal
  - `thinking_time_buffer_minutes>=5` => positive-style signal
- `perception`
  - `session_sequence_hint=application-first` => negative-style signal
  - `session_sequence_hint=theory-first` => positive-style signal
- `understanding`
  - `navigation_mode=linear` => negative-style signal
  - `navigation_mode=free` => positive-style signal
- `input`
  - `input_mode_hint=visual` => negative-style signal
  - `input_mode_hint=verbal` => positive-style signal
  - `mixed` => no signal

## Backend Changes

### 1) Extend `/adapt-learning-path` (no new endpoint)
Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/api_schemas.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`

Request changes:
- `new_learner_profile: Optional[str] = None`
- `force: bool = False`

Response additions (non-breaking):
- `adaptation: {status, applied, reason, trigger_sources, fingerprint, cooldown_remaining_secs}`

Modes:
- explicit mode (profile provided): compare/update using provided profile.
- auto mode (profile omitted): use stored profile + performance-updated vectors.

### 2) Add adaptation state persistence
Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/utils/store.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`

Add `goal.adaptation_state`:
- `last_applied_fingerprint`
- `last_failed_fingerprint`
- `last_failed_at`
- `last_result`
- `last_reason`
- `evidence_windows` (rolling per key)
- `daily_movement_budget` (per dim with window start)

Default normalization:
- goals missing this object receive lazy defaults on read/write.

### 3) Stable fingerprint/idempotency
File:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`

Canonical fingerprint payload (sorted JSON, no timestamps):
- `goal_id`
- `band_state_by_dim` (post-hysteresis classification)
- `evidence_signature_by_key` (compact counts/status, stable ordering)
- `path_version` (`goal.updated_at` or monotonic revision)
- `mode` (`auto|explicit`)

Idempotency:
- same fingerprint as `last_applied_fingerprint` => noop
- failed same fingerprint within cooldown => cooldown skip

### 4) Concurrency safety
Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/utils/store.py`

Apply path:
- acquire per-goal in-process lock
- perform compare-and-set on `goal.updated_at` before write (or store-level revision increment check)
- if revision changed, recompute once then apply

Assumption documented:
- single-process is strongest guarantee; CAS path included for multi-worker tolerance.

### 5) Snapshot lifecycle hardening
File:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`

Rules:
- snapshot used only for preference-change evaluation.
- clear snapshot after adaptation apply or explicit no-op decision.
- ignore snapshot older than 24h.
- if no meaningful preference trigger, clear snapshot to avoid sticky suggestions.

### 6) Add `input_mode_hint` to learning-path contract
Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/learning_plan_generator/schemas.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/learning_plan_generator/prompts/learning_path_scheduling.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/modules/learning_plan_generator/agents/learning_path_scheduler.py`

Changes:
- schema field: `input_mode_hint: Literal["visual","verbal","mixed"] = "mixed"`
- prompt enforces setting field based on `fslsm_input` band
- deterministic post-processing sets/normalizes field
- backward compatibility: missing old sessions default to `mixed`

### 7) Remove manual reschedule API surface
Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/main.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/api_schemas.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/utils/request_api.py`

Changes:
- remove endpoint `POST /reschedule-learning-path`
- remove `LearningPathReschedulingRequest`
- remove frontend mapping/wrapper for reschedule
- keep internal reschedule helper used by adaptation pipeline.

## Frontend Changes

Files:
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/pages/learning_path.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/pages/knowledge_document.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/pages/learner_profile.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/utils/request_api.py`
- `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/frontend/utils/state.py`

Changes:
1. Remove local adaptation flags and manual adaptation CTA.
2. On Learning Path render, use backend runtime signal; when suggested, call `/adapt-learning-path` in auto mode.
3. Remove re-schedule expander and `if_rescheduling_learning_path`.
4. Reorder sections:
   - Current Goal/Progress
   - Plan Quality
   - Module Map
   - Learning Journey
   - Learning Sessions
5. Narrative fix:
   - first upcoming session => “First, you’ll explore …”
   - subsequent upcoming => “Next, you’ll explore …”

## Public API / Type Changes
1. `POST /adapt-learning-path` request:
- `new_learner_profile` optional
- `force` optional
2. `POST /adapt-learning-path` response:
- additive `adaptation` status object
3. Remove public `POST /reschedule-learning-path`.
4. `SessionItem` adds `input_mode_hint`.

## Tests and Scenarios

### Adaptation core
1. Band crossing with hysteresis triggers once; near-threshold jitter does not flap.
2. `0.9 -> 0.7` no trigger if still strong band; `0.7 -> 0.5` triggers when crossing into mild band.
3. Stable fingerprint prevents duplicate adaptation.
4. Failed fingerprint cooldown prevents hammer retries.
5. CAS/locking prevents double-apply under concurrent calls.

### FSLSM update logic
6. Evidence tracked across path by `(dimension, sign)`, not per session.
7. Penalty applies at `2 severe failures in last 3`.
8. Recovery applies at `2 strong successes in last 3`.
9. Daily movement cap enforced.
10. Only session-signaled dimensions are updated.

### Schema/backward compatibility
11. New sessions include `input_mode_hint`.
12. Old sessions without `input_mode_hint` default to `mixed` and do not break.

### Frontend UX
13. No manual re-schedule/adapt controls shown.
14. Plan Quality appears before Module Map/Journey.
15. First upcoming journey line starts with “First”.

### API cleanup
16. `/reschedule-learning-path` returns 404 after removal.
17. Existing explicit `/adapt-learning-path` calls remain functional.

## Assumptions and Defaults
1. Hysteresis margin fixed at `0.02`.
2. Severe failure threshold remains `score < threshold * 0.8`.
3. Strong success threshold set to `score >= threshold + 10`.
4. Adaptation cooldown default `300s`.
5. Snapshot TTL `24h`.
6. Single-process backend is primary deployment target; CAS included for multi-worker tolerance.
