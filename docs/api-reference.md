# Ami API Reference

This document provides a simplified payload reference for each backend endpoint — what you send and what you get back. For full request/response schemas (including field types and validation rules), see the OpenAPI docs at `http://localhost:8000/docs` or the endpoint map in [`backend/README.md`](../backend/README.md).

## Common Request Fields

All generation and AI endpoints accept two optional override fields:

| Field | Description |
|---|---|
| `model_provider` | LLM provider to use (`"openai"`, `"together"`, `"deepseek"`) |
| `model_name` | Model name override (e.g., `"gpt-4o"`) |

If omitted, the backend uses its configured defaults (`gpt-4o` via OpenAI by default).

Several endpoints accept `learner_profile` and `learner_information` as **JSON strings** (serialized objects), not nested objects. The full schema for these objects is in the OpenAPI docs.

---

## 1. Auth

| Endpoint | Input | Output |
|---|---|---|
| `POST /auth/register` | `username`, `password` | `access_token` (JWT) |
| `POST /auth/login` | `username`, `password` | `access_token`, `user_id`, `username` |
| `GET /auth/me` | Bearer token (Authorization header) | `user_id`, `username` |
| `DELETE /auth/user` | Bearer token (Authorization header) | 200 confirmation |

---

## 2. Goals

| Endpoint | Input | Output |
|---|---|---|
| `GET /goals/{user_id}` | — | List of goal objects |
| `POST /goals/{user_id}` | Goal fields (see below) | Created goal with `id` |
| `PATCH /goals/{user_id}/{goal_id}` | Any goal fields to update (all optional) | Updated goal |
| `DELETE /goals/{user_id}/{goal_id}` | — | 200 confirmation |

**Goal object fields** (what the UI reads):

| Field | Description |
|---|---|
| `id` | Goal identifier |
| `learning_goal` | Goal text string |
| `skill_gaps` | List of skill gap objects |
| `goal_assessment` | Vagueness/mastery assessment from skill gap run |
| `bias_audit` | Bias audit result from skill gap run |
| `profile_fairness` | Fairness validation result |
| `learning_path` | List of session objects |
| `plan_agent_metadata` | Agentic plan quality metadata |
| `learner_profile` | Full learner profile object for this goal |
| `is_completed` | Whether all sessions are completed |

---

## 3. Profile

| Endpoint | Input | Output |
|---|---|---|
| `GET /profile/{user_id}` | Query: `goal_id` (optional) | `learner_profile` object |
| `PUT /profile/{user_id}/{goal_id}` | `learner_profile` object | Updated profile |
| `POST /sync-profile/{user_id}/{goal_id}` | — | Merged profile (cross-goal mastery + FSLSM propagation) |

---

## 4. Skill Gap Analysis

| Endpoint | Input | Output |
|---|---|---|
| `POST /identify-skill-gap-with-info` | `learning_goal`, `learner_information`, `skill_requirements` (opt) | `skill_gaps[]`, `goal_assessment`, `retrieved_sources[]` |
| `POST /audit-skill-gap-bias` | `learner_information`, `skill_gaps` (JSON string) | `bias_audit` object |
| `POST /refine-learning-goal` | `learning_goal`, `learner_information` | `refined_goal`, `was_refined` |

**`goal_assessment` fields:**

| Field | Description |
|---|---|
| `is_vague` | Whether the goal was too vague to produce precise gaps |
| `is_all_mastered` | Whether the learner already masters all required skills |
| `suggestions` | List of suggestions if goal is vague |

**`bias_audit` fields:**

| Field | Description |
|---|---|
| `overall_risk` | Risk level: `"low"`, `"medium"`, or `"high"` |
| `flags` | List of detected bias flags |

---

## 5. Profile Generation and Updates

| Endpoint | Input | Output |
|---|---|---|
| `POST /create-learner-profile-with-info` | `learning_goal`, `learner_information`, `skill_gaps` (JSON string), `user_id` (opt), `goal_id` (opt) | `learner_profile` |
| `POST /validate-profile-fairness` | `learner_profile` (JSON string), `learner_information`, `persona_name` (opt) | `profile_fairness` |
| `POST /update-learning-preferences` | `learner_profile` (JSON string), `learner_interactions`, `learner_information` (opt) | Updated `learner_profile` — FSLSM dimensions only |
| `POST /update-learner-information` | `learner_profile` (JSON string), `edited_learner_information`, `resume_text` (opt) | Updated `learner_profile` — background/bio only |
| `POST /update-learner-profile` | `learner_profile` (JSON string), `learner_interactions`, `learner_information`, `session_information` | Full updated `learner_profile` |
| `POST /update-cognitive-status` | `learner_profile` (JSON string), `session_information` | Updated `learner_profile` — SOLO level only |

**`learner_profile` key fields for UI:**

| Field | Description |
|---|---|
| `cognitive_status.solo_level` | Current SOLO taxonomy level |
| `learning_preferences.fslsm_processing` | Active (negative) ↔ Reflective (positive), range −1 to +1 |
| `learning_preferences.fslsm_perception` | Sensing (negative) ↔ Intuitive (positive) |
| `learning_preferences.fslsm_input` | Visual (negative) ↔ Verbal (positive) |
| `learning_preferences.fslsm_understanding` | Sequential (negative) ↔ Global (positive) |
| `behavioral_patterns` | Engagement and learning behavior summary |
| `mastered_skills` | List of skills the learner has mastered |

**`profile_fairness` fields:**

| Field | Description |
|---|---|
| `overall_fairness_risk` | `"low"`, `"medium"`, or `"high"` |
| `fairness_flags` | Demographic or assumption bias flags |
| `fslsm_deviation_flags` | FSLSM dimension outlier flags |

---

## 6. Learning Path

| Endpoint | Input | Output |
|---|---|---|
| `POST /schedule-learning-path-agentic` | `learner_profile` (JSON string), `session_count` | `learning_path[]`, `plan_agent_metadata` |
| `POST /adapt-learning-path` | `learner_profile` (JSON string), current learning path info | `learning_path[]`, `adaptation_decision`, `reasoning` |
| `GET /goal-runtime-state/{user_id}` | Query: `goal_id` | Sessions with lock/mastery/adaptation state |

**`plan_agent_metadata` fields:**

| Field | Description |
|---|---|
| `evaluation.pass` | Whether the plan passed quality gate |
| `evaluation.issues` | List of quality issues found |
| `evaluation.feedback_summary` | Summary of evaluator feedback |
| `refinement_iterations` | How many refinement passes ran |

**Runtime state session fields:**

| Field | Description |
|---|---|
| `is_locked` | Session cannot be started yet (linear mode only) |
| `is_mastered` | Learner passed the mastery quiz |
| `mastery_score` | Quiz score as a percentage |
| `adaptation.suggested` | Whether adaptation is recommended |
| `adaptation.reason` | Why adaptation is suggested |

**`adaptation_decision` values:** `"KEEP"`, `"ADJUST_FUTURE"`, `"REGENERATE"`

---

## 7. Learning Content and Sessions

| Endpoint | Input | Output |
|---|---|---|
| `GET /learning-content/{user_id}/{goal_id}/{session_index}` | — | Cached content object, or 404 if not cached |
| `DELETE /learning-content/{user_id}/{goal_id}/{session_index}` | — | 200 (clears the content cache for that session) |
| `POST /generate-learning-content` | `learner_profile` (JSON string), `learning_path` (JSON string), `learning_session` (JSON string), `with_quiz` (bool), `use_search` (bool), `goal_context` (opt) | Content object (see below) |
| `POST /session-activity` | `user_id`, `goal_id`, `session_index`, `event_type` | 200 |
| `POST /complete-session` | `user_id`, `goal_id`, `session_index`, `session_end_time` (opt) | `{goal}` — full updated goal object |
| `POST /submit-content-feedback` | `user_id`, `goal_id`, `feedback` | Updated goal object |

**`event_type` values for `/session-activity`:** `"start"`, `"heartbeat"`, `"end"`

**Content object fields:**

| Field | Description |
|---|---|
| `sections` | List of document sections (title, body markdown) |
| `quiz` | Quiz object with questions by type |
| `audio_url` | URL to generated MP3 audio (auditory learners only) |
| `content_format` | `"standard"`, `"visual_enhanced"`, or `"audio_enhanced"` |
| `view_model` | Structured rendering model with pre-parsed sections |

---

## 8. Assessment and Mastery

| Endpoint | Input | Output |
|---|---|---|
| `POST /evaluate-mastery` | `user_id`, `goal_id`, `session_index`, `quiz_answers` (object) | `score`, `is_mastered`, `mastery_threshold`, `feedback`, `open_ended_feedback[]` |
| `GET /session-mastery-status/{user_id}` | Query: `goal_id` | Sessions with mastery status and scores |
| `GET /quiz-mix/{user_id}` | Query: `goal_id`, `session_index` | Quiz type distribution for the session |

**`open_ended_feedback` item fields:**

| Field | Description |
|---|---|
| `solo_level` | Assessed SOLO level (e.g., `"Relational"`) |
| `score` | Fractional score (0.0–1.0) |
| `feedback` | Qualitative explanation of the assessment |

---

## 9. Analytics

| Endpoint | Input | Output |
|---|---|---|
| `GET /dashboard-metrics/{user_id}` | Query: `goal_id` | `overall_progress`, `skill_radar`, `session_time_series[]`, `mastery_time_series[]` |
| `GET /behavioral-metrics/{user_id}` | Query: `goal_id` | Behavioral metrics object (see below) |

**Behavioral metrics fields:**

| Field | Description |
|---|---|
| `sessions_completed` | Number of sessions the learner completed |
| `total_sessions_in_path` | Total sessions in the learning path |
| `sessions_learned` | Sessions where mastery was achieved |
| `avg_session_duration_sec` | Average time per session in seconds |
| `total_learning_time_sec` | Cumulative learning time in seconds |
| `motivational_triggers_count` | How many motivational trigger events occurred |
| `mastery_history` | List of mastery results over time |
| `latest_mastery_rate` | Most recent mastery rate (0.0–1.0) |

---

## 10. Ami Chatbot

| Endpoint | Input | Output |
|---|---|---|
| `POST /chat-with-tutor` | See below | `response` text; if `return_metadata=true`: also `profile_updated`, `updated_learner_profile` |

**Input fields:**

| Field | Description |
|---|---|
| `messages` | JSON string of `[{"role": "user"/"assistant", "content": "..."}]` |
| `learner_profile` | JSON string of current learner profile |
| `user_id` | User identifier (enables profile updates) |
| `goal_id` | Current goal identifier |
| `session_index` | Current session index (enables session content retrieval) |
| `use_web_search` | Enable ephemeral web search tool |
| `use_vector_retrieval` | Enable verified-content RAG tool |
| `use_media_search` | Enable media resource search tool |
| `allow_preference_updates` | Allow signal-gated FSLSM profile updates |
| `return_metadata` | Return structured response with profile update info |
| `learner_information` | Learner background context string |

---

## 11. Utilities

| Endpoint | Input | Output |
|---|---|---|
| `GET /personas` | — | List of persona objects (name, description, FSLSM dimension values) |
| `GET /config` | — | App config (skill levels, FSLSM thresholds, default session count, default LLM) |
| `POST /extract-pdf-text` | Multipart form: PDF file | `text` — extracted text string |
| `GET /list-llm-models` | — | Available models grouped by provider |
| `POST /events/log` | `user_id`, `event_type`, payload | 200 confirmation |
| `GET /events/{user_id}` | — | List of event objects |
| `DELETE /user-data/{user_id}` | — | 200 (deletes all learning data; auth account remains) |
