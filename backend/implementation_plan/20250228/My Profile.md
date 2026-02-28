## Learner Profile Edit Refactor (Revised for Gaps and Bug Risks)

### Summary
Move profile editing into an `Edit Profile` modal in learner profile, with two backend-driven modes:
1. `FSLSM updates` via sliders only.
2. `Enhance learner information ONLY` via direct text edit and/or resume upload.

This revision adds explicit safeguards for XSS/layout breakage, deterministic cross-goal propagation, widget key collisions, mutation safety, and large-resume handling.

### Key Revisions vs Previous Plan
1. Remove unsafe HTML rendering for editable learner information to prevent injection/layout breakage.
2. Replace nondeterministic cross-goal learner-information merge behavior with explicit deterministic propagation.
3. Use distinct Streamlit widget keys for read-only vs edit sliders.
4. Ensure deep-copy semantics in all propagation/update operations.
5. Add backend input compaction/truncation guardrails for edited text and resume text.

### API / Contract Changes
1. Keep existing `POST /update-learning-preferences` and support structured slider payload:
   `{"update_mode":"fslsm_slider_override","slider_values":{...}}`.
2. Add `POST /update-learner-information` with request fields:
   `learner_profile`, `edited_learner_information`, `resume_text`, `user_id`, `goal_id`.
3. Response for new endpoint returns selected goal’s updated `learner_profile`.
4. Compatibility: old preference payloads still accepted.

### Backend Plan
1. Add input utility module  
   [profile_edit_inputs.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/learner_profiler/utils/profile_edit_inputs.py)  
   Responsibilities:
   - Normalize and clamp FSLSM slider values to canonical keys.
   - Compose info-update input using text-primary merge rule.
   - Compact whitespace and truncate inputs (defaults: edited text 8k chars, resume text 20k chars).

2. Extend learner-profiler agent path for strict info-only updates  
   [adaptive_learning_profiler.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/learner_profiler/agents/adaptive_learning_profiler.py)  
   [adaptive_learning_profiler.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/learner_profiler/prompts/adaptive_learning_profiler.py)  
   Rules:
   - Only `learner_information` may change.
   - Re-apply original `learning_goal`, `goal_display_name`, `cognitive_status`, `learning_preferences`, `behavioral_patterns` after LLM output.

3. Add endpoint schema  
   [api_schemas.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/api_schemas.py)

4. Add endpoint implementation  
   [main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py)  
   Flow:
   - Parse and normalize payload.
   - Snapshot selected goal profile for adaptation invariants.
   - Execute strict info-only updater.
   - Persist selected goal profile.
   - Deterministically propagate same `learner_information` to all user profiles via explicit store helper.
   - Return updated selected-goal profile.

5. Add deterministic propagation helper in store  
   [store.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/utils/store.py)  
   New helper: propagate learner info across goals using explicit value and deep-copied profiles.
   Revision in merge behavior:
   - Stop “last non-empty wins” learner-information merge.
   - Leave merge for mastered skills/preferences/behavioral patterns only.

6. Preference endpoint slider override enforcement  
   [main.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/main.py)  
   - If `update_mode=fslsm_slider_override`, apply normalized slider values after LLM response.
   - Keep snapshot/sign-flip reset flow unchanged.

### Frontend Plan
1. Replace standalone additional-info section with modal trigger  
   [learner_profile.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/pages/learner_profile.py)

2. Modal content
   - Mode A: editable FSLSM sliders only.
   - Mode B: direct editable learner-information textarea prefilled from current profile, plus optional resume upload.

3. Rendering safety fix
   - Render learner information as plain/safe text (no raw HTML interpolation with `unsafe_allow_html=True`).

4. Streamlit key isolation
   - Read-only display slider keys prefixed `view_...`.
   - Edit modal slider keys prefixed `edit_...`.

5. API client updates  
   [request_api.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/frontend/utils/request_api.py)  
   - Add `update_learner_information(...)`.
   - Add new endpoint name constant.
   - Keep existing PDF extraction path.

### Validation and Acceptance Rules
1. Mode B submit blocked only when both edited text is empty and no resume text is provided.
2. If both text and resume are provided, text is primary and resume enriches missing details.
3. Non-`learner_information` fields must be byte-for-byte equivalent before/after Mode B update.
4. Cross-goal learner_information is identical immediately after Mode B success.
5. No duplicate widget key errors in learner profile page.

### Test Plan
1. Backend unit tests for input normalization/clamping/truncation.
2. Backend endpoint tests for `/update-learner-information`:
   - selected goal updated.
   - all-goal propagation applied.
   - strict preservation of other profile sections.
3. Backend regression test for merge logic to confirm learner-information is no longer nondeterministically overwritten.
4. Backend tests for slider override branch in `/update-learning-preferences`.
5. Frontend manual tests:
   - modal launch.
   - two modes work.
   - safe learner-information rendering with HTML-like input.
   - direct text only, resume only, and text+resume paths.

### Assumptions and Defaults
1. All-goal learner-information propagation is product-required behavior.
2. Slider range remains `[-1.0, 1.0]` with `0.1` step.
3. Input truncation defaults are sufficient for model/context safety and can be moved to config later if needed.
