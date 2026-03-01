# React Frontend — API Flow Reference

This document describes the API call sequences and UI rendering rules for each page in the Ami application. Use it as a guide for implementing the React frontend. Full request/response schemas are available at `http://localhost:8000/docs` and the backend module overview is in [`backend/README.md`](../backend/README.md).

**Backend base URL:** `http://localhost:8000` (configurable via `BACKEND_ENDPOINT`)
**Media/static URLs:** use `BACKEND_PUBLIC_ENDPOINT` as base for any `/static/...` paths rendered in the browser.

---

## App Pages Overview

| Page | Entry Condition | Purpose |
|---|---|---|
| Login / Register | Not authenticated | Authenticate or create an account |
| Onboarding | Authenticated, no goals yet | Collect persona, learning goal, optional resume |
| Skill Gap | After onboarding, or adding a new goal | Identify skill gaps and create learner profile |
| Goal Management | Any time post-onboarding | Add, switch, edit, or delete learning goals |
| Learning Path | Active goal with skill gaps identified | View and navigate the personalized session plan |
| Learning Session | Session launched from Learning Path | Read content, listen to audio, take quizzes |
| Learner Profile | Any time post-onboarding | View profile, edit learning style or background info |
| Analytics Dashboard | Any time post-onboarding | View learning progress and metrics |
| Ami Chatbot | Available during Learning Session | Ask questions to the AI tutor |

---

## 1. Authentication

### Register

1. `POST /auth/register` with username and password
2. On success: store `userId` and `auth_token`, navigate to Onboarding

### Login

1. `POST /auth/login` with username and password
2. On success: store `userId` and `auth_token`
3. `GET /goals/{user_id}` to load existing goals
4. If goals exist → navigate to Learning Path (or Goal Management); otherwise → navigate to Onboarding

### Logout

Clear local auth state and navigate to Login.

### Delete Account

Requires `auth_token` to be present (show error if missing, do not call backend).

1. Show confirmation dialog
2. On confirm: `DELETE /auth/user` with `Authorization: Bearer <token>`
3. Clear state and navigate to Login

---

## 2. App Startup

These calls happen once on app load, before rendering any page content.

1. `GET /list-llm-models` — populate model selector in settings UI
2. `GET /config` — load global config values (skill levels, session count defaults, FSLSM thresholds)

---

## 3. Onboarding

**Entry:** User is authenticated and has no goals.

1. `GET /personas` — render persona selection cards
2. User selects a persona and types a learning goal
3. Optional resume upload: `POST /extract-pdf-text` (multipart) — save extracted text locally
4. On **Begin Learning**: validate that a goal and persona are selected, then navigate to Skill Gap

---

## 4. Skill Gap

**Entry:** Navigated from Onboarding (new goal) or from Goal Management (adding a goal).

Analysis runs automatically on page load when the current goal has no skill gaps yet.

### Analysis sequence

1. `POST /identify-skill-gap-with-info` — returns `skill_gaps`, `goal_assessment`, `retrieved_sources`, `goal_context`
   - If `goal_assessment.auto_refined` is true, replace the displayed learning goal with `goal_assessment.refined_goal`
2. Immediately after: `POST /audit-skill-gap-bias` — returns `bias_audit`

### Local skill editing (no API call)

Users can adjust each skill's required level, current level, and `is_gap` status locally.

- **Mark as Gap** toggle is disabled when `is_gap` is already false
- **Schedule Learning Path** button is disabled until at least one skill has `is_gap == true`

### On "Schedule Learning Path"

1. `POST /create-learner-profile-with-info` (only if no profile exists yet)
2. `POST /validate-profile-fairness` — returns `profile_fairness` (only called from this Onboarding path, not from Goal Management)
3. `POST /goals/{user_id}` — persist the full goal (gaps, assessment, context, bias audit, fairness, profile)
4. `POST /sync-profile/{user_id}/{goal_id}`
5. Navigate to Learning Path

---

## 5. Goal Management

**Entry:** Any time post-onboarding.

1. Goals are already loaded from `/goals/{user_id}` at login

### Add a new goal

Runs the same pipeline as Skill Gap with one difference: `POST /validate-profile-fairness` is **not** called here.

1. Optional: `POST /refine-learning-goal` — AI-assisted goal refinement
2. `POST /identify-skill-gap-with-info`
3. `POST /audit-skill-gap-bias`
4. `POST /create-learner-profile-with-info`
5. `POST /goals/{user_id}`
6. `POST /sync-profile/{user_id}/{goal_id}`

### Edit goal text

`PATCH /goals/{user_id}/{goal_id}` with updated `learning_goal`

### Delete goal

`DELETE /goals/{user_id}/{goal_id}`

### Switch active goal

`POST /sync-profile/{user_id}/{goal_id}` — updates shared profile state to the selected goal

---

## 6. Learning Path

**Entry:** Active goal exists with skill gaps identified.

### On page load

1. `GET /goal-runtime-state/{user_id}?goal_id=<id>` — get live session lock/mastery state

### Schedule path (first time only)

If the goal has no `learning_path` yet:

1. `POST /schedule-learning-path-agentic`
2. `PATCH /goals/{user_id}/{goal_id}` — persist `learning_path` and `plan_agent_metadata`

### Automatic adaptation

If runtime state returns `adaptation.suggested == true`:

1. `POST /adapt-learning-path`
2. If response `adaptation.status == "applied"`: update `learning_path` and `plan_agent_metadata`, then `PATCH /goals/{user_id}/{goal_id}`

### Session card rendering

Each session card reads from `goal-runtime-state`:

| Field | UI behavior |
|---|---|
| `is_locked == true` | Show "Locked" label, disable the launch button |
| `is_mastered == true` | Show mastery badge with `mastery_score` |
| `adaptation.suggested == true` | Show adaptation in-progress banner |
| `adaptation.message` | Display the adaptation message text |

### FSLSM-conditional sections

Read from `learner_profile.learning_preferences.fslsm_dimensions.fslsm_input` (no API call):

- `≤ −0.3` → show **Module Map** view
- `≥ +0.3` → show **Your Learning Journey** narrative view
- Between `−0.3` and `+0.3` → show neither

### Plan Quality panel

Show only when `goal.plan_agent_metadata` exists. Render from:

- `plan_agent_metadata.evaluation.pass` — overall pass/fail
- `plan_agent_metadata.evaluation.issues[]` — list of issues
- `plan_agent_metadata.evaluation.feedback_summary` — summary text
- `plan_agent_metadata.refinement_iterations` — number of reflexion passes

### Launch a session

1. `POST /session-activity` with `event_type: "start"` and session identifiers
2. Navigate to Learning Session

---

## 7. Learning Session

**Entry:** Launched from a session card on Learning Path.

### Content loading

1. `GET /learning-content/{user_id}/{goal_id}/{session_index}` — check for cached content
2. If not found: `POST /generate-learning-content` — generate and cache content

### Rendering rules

| Condition | UI behavior |
|---|---|
| `content_format == "audio_enhanced"` | Show audio-enhanced banner; render audio player if `audio_url` present |
| `content_format == "visual_enhanced"` | Show visual-enhanced banner |
| `view_model.sections` present | Render document sections from `view_model.sections` and `view_model.references` |
| `view_model` absent | Fall back to raw section parsing |

Sidebar table of contents and per-section navigation are local UI behavior (no API call).

### During the session

- **Heartbeat:** `POST /session-activity` with `event_type: "heartbeat"` at regular intervals
  - Response may include `trigger.show` and `trigger.message` — display as a motivational nudge if present
- **Leave (back button):** `POST /session-activity` with `event_type: "end"` → navigate to Learning Path
- **Regenerate content:** `POST /session-activity` (end) → `DELETE /learning-content/{user_id}/{goal_id}/{session_index}` → reload content

### Quiz

1. `POST /evaluate-mastery` with all quiz answers
2. Render from response: `score_percentage`, `is_mastered`, `threshold`, and optionally `short_answer_feedback`, `open_ended_feedback`
3. Store mastery result locally in the current session

### Complete session

Button is disabled until mastered when `navigation_mode == "linear"`.

1. `POST /complete-session`
2. Replace current goal aggregate with `response.goal`
3. Navigate back to Learning Path

### Session feedback

1. `POST /submit-content-feedback`
2. Refresh current goal from `response.goal`

---

## 8. Learner Profile

**Entry:** Any time post-onboarding.

Profile data is sourced from the goal aggregate already loaded via `/goals`.

### Behavioral metrics

`GET /behavioral-metrics/{user_id}?goal_id=<id>`

Rendered fields: `sessions_completed`, `total_sessions_in_path`, `avg_session_duration_sec`, `total_learning_time_sec`, `mastery_history`, `latest_mastery_rate`

### Fairness display

Always show an ethical disclaimer banner. Additional display logic:

| Condition | UI behavior |
|---|---|
| `goal.profile_fairness` missing | Show fallback disclaimer text only, no details section |
| `overall_fairness_risk` is `"medium"` or `"high"` | Show warning summary with flagged and checked item counts |
| `fairness_flags` or `fslsm_deviation_flags` non-empty | Show details expander |

### Edit Profile

Entry: user clicks **Edit Profile** button → opens modal with a mode selector.

**Learning Preferences mode** (FSLSM sliders):

1. `POST /update-learning-preferences` with current profile and updated slider values
2. Replace goal profile with `response.learner_profile`
3. Reload goals from `/goals/{user_id}`

**Learner Information mode** (text + optional resume):

1. Optional: `POST /extract-pdf-text` (if resume uploaded)
2. `POST /update-learner-information` with profile, edited text, and resume text
3. Replace goal profile with `response.learner_profile`
4. Reload goals from `/goals/{user_id}`

Disable submit if both edited text and resume text are empty.

### Restart onboarding (keeps account)

Show confirmation dialog. On confirm:

1. `DELETE /user-data/{user_id}`
2. Clear local session state
3. Navigate to Onboarding

---

## 9. Analytics Dashboard

**Entry:** Any time post-onboarding.

1. `GET /dashboard-metrics/{user_id}?goal_id=<id>`
2. Render: `overall_progress`, `skill_radar` (labels, current_levels, required_levels), `session_time_series[]`, `mastery_time_series[]`

---

## 10. Ami Chatbot

Available during Learning Session and other pages.

On each user message submit (rolling window of last 20 messages):

1. `POST /chat-with-tutor` with:
   - `messages`, `learner_profile`, `user_id`, `goal_id`, `session_index` (if in a session), `learner_information`
   - feature flags: `use_web_search`, `use_vector_retrieval`, `use_media_search`, `allow_preference_updates`
   - `return_metadata: true`
2. Render `response` text in the chat
3. If `updated_learner_profile` is present in the response, replace the active goal's profile locally

---

## 11. API Endpoint Reference

| Endpoint | Page | Trigger |
|---|---|---|
| `POST /auth/register` | Login | Register form submit |
| `POST /auth/login` | Login | Login form submit |
| `DELETE /auth/user` | Profile | Delete account confirm |
| `GET /list-llm-models` | Global | App startup |
| `GET /config` | Global | App startup |
| `GET /personas` | Onboarding | Page load |
| `POST /extract-pdf-text` | Onboarding, Profile | Resume upload |
| `POST /refine-learning-goal` | Goal Management | AI refinement button |
| `POST /identify-skill-gap-with-info` | Skill Gap, Goal Management | Auto on page load |
| `POST /audit-skill-gap-bias` | Skill Gap, Goal Management | After skill gap identified |
| `POST /create-learner-profile-with-info` | Skill Gap, Goal Management | Before persisting goal |
| `POST /validate-profile-fairness` | Skill Gap (onboarding path only) | Before persisting goal |
| `GET /goals/{user_id}` | Global | Login, after profile edits |
| `POST /goals/{user_id}` | Skill Gap, Goal Management | Schedule Learning Path |
| `PATCH /goals/{user_id}/{goal_id}` | Learning Path | After scheduling or adaptation |
| `DELETE /goals/{user_id}/{goal_id}` | Goal Management | Delete goal |
| `POST /sync-profile/{user_id}/{goal_id}` | Skill Gap, Goal Management | After goal created or switched |
| `GET /goal-runtime-state/{user_id}` | Learning Path | Page load |
| `POST /schedule-learning-path-agentic` | Learning Path | No learning path exists |
| `POST /adapt-learning-path` | Learning Path | adaptation.suggested == true |
| `GET /learning-content/{user_id}/{goal_id}/{session_index}` | Learning Session | Page load (cache check) |
| `POST /generate-learning-content` | Learning Session | Cache miss |
| `DELETE /learning-content/{user_id}/{goal_id}/{session_index}` | Learning Session | Regenerate action |
| `POST /session-activity` | Learning Session | Start, heartbeat, end events |
| `POST /evaluate-mastery` | Learning Session | Quiz submit |
| `POST /complete-session` | Learning Session | Complete button |
| `POST /submit-content-feedback` | Learning Session | Feedback form submit |
| `GET /dashboard-metrics/{user_id}` | Analytics | Page load |
| `GET /behavioral-metrics/{user_id}` | Profile | Page load |
| `GET /profile/{user_id}` | Profile | Recovery path only |
| `POST /update-learning-preferences` | Profile | FSLSM slider save |
| `POST /update-learner-information` | Profile | Learner info save |
| `DELETE /user-data/{user_id}` | Profile | Restart onboarding confirm |
| `POST /chat-with-tutor` | Chatbot | Message submit |
