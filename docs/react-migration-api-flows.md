# React Migration: Key Flows and API Reference

This document maps each user-facing flow to the API calls it requires. For each call it specifies the **frontend inputs** the user provides and the **response shape + display guidance** for the React implementation.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Onboarding](#2-onboarding)
3. [Skill Gap Analysis](#3-skill-gap-analysis)
4. [Learning Path](#4-learning-path)
5. [Learning Session (Knowledge Document)](#5-learning-session-knowledge-document)
6. [Goal Management](#6-goal-management)
7. [Learner Profile](#7-learner-profile)
8. [Dashboard / Analytics](#8-dashboard--analytics)
9. [AI Tutor Chat](#9-ai-tutor-chat)
10. [Shared / Utility Endpoints](#10-shared--utility-endpoints)

---

## 1. Authentication

### Flow overview
Users must register or log in before accessing any other feature. On success the backend returns a JWT token, which must be stored (e.g. in React context / localStorage) and sent as a `Bearer` header on all subsequent requests.

---

### 1.1 Register — `POST /auth/register`

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Username field | `<input type="text">` | Required |
| Password field | `<input type="password">` | Required |
| "Register" button | `<button>` | Submits the form |

**Request body**
```json
{ "username": "string", "password": "string" }
```

**Response**
```json
{ "token": "jwt-string", "username": "string" }
```

**Display**
- On success: store `token` + `username` in auth context, redirect to Onboarding.
- On failure (non-200): show an inline error message (e.g. "Username already taken").

---

### 1.2 Login — `POST /auth/login`

**Frontend inputs** — identical to Register above.

**Request / Response** — identical shape to Register.

**Display** — same as Register success handling.

---

### 1.3 Delete Account — `DELETE /auth/user`

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Delete Account" button | `<button>` (destructive) | Opens confirmation dialog |
| Confirmation dialog with "Delete" / "Cancel" | Modal | Requires explicit confirmation |

**Headers required**: `Authorization: Bearer <token>`

**Response**
```json
{ "ok": true }
```

**Display**
- On success: clear auth context, redirect to login/register.
- On failure: show error message from `response.detail`.

---

## 2. Onboarding

### Flow overview
The user enters a learning goal, selects a learning persona, and optionally uploads a PDF resume. No LLM calls happen on this page — the collected data is passed to the Skill Gap flow.

---

### 2.1 Get Personas — `GET /personas`

Called on page mount to populate the persona selection cards.

**Frontend inputs** — none (automatic on load).

**Response**
```json
{
  "personas": {
    "PersonaName": {
      "description": "string",
      "fslsm_dimensions": {
        "fslsm_processing": 0.5,
        "fslsm_perception": -0.3,
        "fslsm_input": 0.0,
        "fslsm_understanding": 0.2
      }
    }
  }
}
```

**Display**
- Render one card per persona key.
- Each card shows the persona name + description.
- The selected persona is highlighted; clicking "Select" toggles selection.

---

### 2.2 Extract PDF Text — `POST /extract-pdf-text` (multipart)

Called when the user uploads a resume PDF.

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| File input | `<input type="file" accept=".pdf">` | Optional |

**Request** — multipart/form-data with key `file`.

**Response**
```json
{ "text": "extracted plain text string" }
```

**Display**
- Show a spinner while uploading.
- On success: show a success toast ("PDF uploaded successfully").
- The extracted text is appended to `learner_information` internally (not displayed directly to the user).

---

### 2.3 Page state passed downstream
After "Begin Learning" is clicked the following is carried forward (not an API call):
- `learning_goal` (text input value)
- `learner_persona` (selected persona name)
- `learner_information` (persona FSLSM prefix + PDF text, combined string)

---

## 3. Skill Gap Analysis

### Flow overview
Using the goal and learner information from Onboarding, the system identifies skill gaps via LLM, runs a bias audit, then creates an initial learner profile. The user can review and adjust skill gap classifications before continuing.

---

### 3.1 Identify Skill Gap — `POST /identify-skill-gap-with-info`

Triggered automatically on page load (if no skill gaps exist yet).

**Frontend inputs** — no manual inputs (uses session data from Onboarding).

**Request body**
```json
{
  "learning_goal": "string",
  "learner_information": "string (JSON or plain text)",
  "llm_type": "gpt4o",
  "method_name": "ami",
  "user_id": "string (optional)",
  "goal_id": 0
}
```

**Response**
```json
{
  "skill_gaps": [
    {
      "name": "Python Basics",
      "current_level": "beginner",
      "required_level": "intermediate",
      "is_gap": true,
      "reason": "string",
      "level_confidence": "high"
    }
  ],
  "goal_assessment": {
    "auto_refined": false,
    "refined_goal": "string",
    "original_goal": "string",
    "is_vague": false,
    "all_mastered": false,
    "suggestion": "string"
  },
  "retrieved_sources": [
    { "title": "string", "source_type": "verified_content", "url": "string" }
  ],
  "goal_context": {}
}
```

**Display**
- Show a loading spinner ("Identifying Skill Gap...") while the request is in-flight.
- If `goal_assessment.auto_refined === true`: show an info banner with original and refined goals.
- If `goal_assessment.is_vague`: show a warning banner with the suggestion.
- If `goal_assessment.all_mastered`: show an info banner indicating all skills are already mastered.
- If `retrieved_sources` is non-empty: show an info banner ("Skill analysis grounded in verified course content") with an expandable list of citations.
- Render skill gap summary: "X skills identified · Y skill gaps".
- Render each skill as a card (see display details below under 3.3).

---

### 3.2 Audit Skill Gap Bias — `POST /audit-skill-gap-bias`

Called automatically after skill gaps are identified.

**Frontend inputs** — none (automatic).

**Request body**
```json
{
  "skill_gaps": "JSON string of skill_gaps dict",
  "learner_information": "string",
  "llm_type": "gpt4o",
  "method_name": "ami"
}
```

**Response**
```json
{
  "ethical_disclaimer": "string",
  "overall_bias_risk": "low | medium | high",
  "flagged_skill_count": 2,
  "audited_skill_count": 8,
  "bias_flags": [
    {
      "skill_name": "string",
      "bias_category": "string",
      "severity": "low | medium | high",
      "explanation": "string",
      "suggestion": "string"
    }
  ],
  "confidence_calibration_flags": [
    { "skill_name": "string", "issue": "string" }
  ]
}
```

**Display**
- Always show `ethical_disclaimer` as an info banner.
- If `overall_bias_risk` is `medium` or `high`: show a warning banner with flagged counts.
- Render an expandable "View bias audit details" section listing bias flags (with severity icons) and calibration warnings.

---

### 3.3 Skill Gap Cards (interactive UI — no API call)

Each skill gap is rendered as an editable card:
| Element | Type | Notes |
|---|---|---|
| Skill name header | Display text | Color-coded (red = gap, green = not a gap) |
| Required Level selector | Pill/chip group | Options: beginner, intermediate, advanced, expert |
| Current Level selector | Pill/chip group | Options: unlearned, beginner, intermediate, advanced, expert |
| "Mark as Gap" toggle | Toggle/switch | Adjusts `is_gap` flag |
| "More Analysis Details" expander | Expandable | Shows reason and confidence |

Changes to level or toggle update local state and re-evaluate `is_gap` without a network call.

---

### 3.4 Refine Learning Goal — `POST /refine-learning-goal`

Available from the Goal Management page as an "AI Refinement" button.

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Learning goal text area | `<textarea>` | Pre-filled with current goal |
| "✨ AI Refinement" button | `<button>` | Triggers the call |

**Request body**
```json
{
  "learning_goal": "string",
  "learner_information": "string",
  "llm_type": "gpt4o",
  "method_name": "ami"
}
```

**Response**
```json
{ "refined_goal": "string" }
```

**Display**
- Show a loading indicator on the button while in-flight.
- On success: replace the goal text area value with `refined_goal`, show a success toast.

---

### 3.5 Create Learner Profile — `POST /create-learner-profile-with-info`

Called when the user clicks "Schedule Learning Path" (after skill gaps are confirmed).

**Frontend inputs** — no manual inputs; uses session data.

**Request body**
```json
{
  "learning_goal": "string",
  "learner_information": "string",
  "skill_gaps": "JSON string",
  "llm_type": "gpt4o",
  "method_name": "ami",
  "user_id": "string (optional)",
  "goal_id": 0
}
```

**Response**
```json
{
  "learner_profile": {
    "learner_information": "string",
    "learning_goal": "string",
    "cognitive_status": {
      "overall_progress": 0,
      "mastered_skills": [],
      "in_progress_skills": []
    },
    "learning_preferences": {
      "fslsm_dimensions": {
        "fslsm_processing": 0.5,
        "fslsm_perception": -0.3,
        "fslsm_input": 0.0,
        "fslsm_understanding": 0.2
      },
      "additional_notes": "string"
    },
    "behavioral_patterns": {
      "system_usage_frequency": "string",
      "session_duration_engagement": "string",
      "motivational_triggers": "string",
      "additional_notes": "string"
    },
    "goal_display_name": "string"
  }
}
```

**Display**
- Show a spinner ("Creating your profile...") while in-flight.
- On success: show a success toast and redirect to Learning Path page.

---

### 3.6 Validate Profile Fairness — `POST /validate-profile-fairness`

Called automatically after the learner profile is created.

**Frontend inputs** — none (automatic).

**Request body**
```json
{
  "learner_profile": "JSON string of profile",
  "learner_information": "string",
  "persona_name": "string",
  "llm_type": "gpt4o"
}
```

**Response**
```json
{
  "ethical_disclaimer": "string",
  "overall_fairness_risk": "low | medium | high",
  "flagged_fields_count": 0,
  "checked_fields_count": 10,
  "fairness_flags": [
    {
      "field_name": "string",
      "fairness_category": "string",
      "severity": "low | medium | high",
      "explanation": "string",
      "suggestion": "string"
    }
  ],
  "fslsm_deviation_flags": [
    {
      "dimension": "string",
      "persona_value": 0.5,
      "profile_value": 0.1,
      "deviation": 0.4
    }
  ]
}
```

**Display** — shown on the Learner Profile page (see section 7).

---

### 3.7 Create Goal — `POST /goals/{user_id}`

Called after the learner profile is created to persist the entire goal (with skill gaps, profile, etc.) to the backend.

**Frontend inputs** — none (automatic).

**Request body** (`GoalCreateRequest`)
```json
{
  "learning_goal": "string",
  "skill_gaps": [],
  "goal_assessment": {},
  "goal_context": {},
  "retrieved_sources": [],
  "bias_audit": {},
  "profile_fairness": {},
  "learning_path": [],
  "learner_profile": {}
}
```

**Response**
```json
{ "id": 1, "learning_goal": "string", ... }
```

**Display** — no direct UI; `id` is stored as `selected_goal_id` and used for subsequent API calls.

---

## 4. Learning Path

### Flow overview
The learning path is generated by an agentic backend endpoint. Once generated it is shown as a grid of session cards. The path may be automatically adapted if the backend signals that an update is needed.

---

### 4.1 Schedule Learning Path (Agentic) — `POST /schedule-learning-path-agentic`

Called automatically when the user arrives at the Learning Path page and no path exists yet.

**Frontend inputs** — none (automatic).

**Request body**
```json
{
  "learner_profile": "JSON string of learner profile",
  "session_count": 8
}
```

**Response**
```json
{
  "learning_path": [
    {
      "id": "session-uuid",
      "title": "string",
      "abstract": "string",
      "if_learned": false,
      "is_mastered": false,
      "mastery_score": null,
      "mastery_threshold": 70,
      "navigation_mode": "linear | free",
      "associated_skills": ["string"],
      "desired_outcome_when_completed": [
        { "name": "string", "level": "intermediate" }
      ],
      "has_checkpoint_challenges": false,
      "thinking_time_buffer_minutes": 0,
      "session_sequence_hint": "theory-first | application-first | null"
    }
  ],
  "agent_metadata": {
    "evaluation": {
      "pass": true,
      "issues": [],
      "feedback_summary": {}
    },
    "refinement_iterations": 1
  }
}
```

**Display**
- Show a spinner ("Generating learning path...") while in-flight.
- On success: show a toast and render the session grid.
- `agent_metadata.evaluation` → show in a collapsible "Plan Quality" section:
  - If `pass: true`: green success badge with iteration count.
  - If `pass: false`: yellow warning badge with listed issues.

**Session cards display**
- Title with color indicator (green = completed, red = not started).
- Abstract in an expandable panel.
- Associated skills and desired outcomes listed.
- `session_sequence_hint` shown as a caption if present.
- `mastery_score` badge shown if available.
- "Learning" (primary) or "Completed" (secondary) action button.
- Locked sessions show a disabled "Locked" button with caption.

**Additional adaptive displays** (based on `fslsm_input` dimension):
- Visual learners (`fslsm_input ≤ -0.3`): also render a Module Map — a color-coded grid (green = done/mastered, grey = locked, red = pending).
- Verbal learners (`fslsm_input ≥ 0.3`): also render a narrative overview listing sessions as prose chapters.

---

### 4.2 Adapt Learning Path — `POST /adapt-learning-path`

Called automatically when the backend signals `adaptation.suggested === true` in the runtime state.

**Frontend inputs** — none (automatic, triggered by polling runtime state).

**Request body**
```json
{
  "user_id": "string",
  "goal_id": 1,
  "force": false,
  "new_learner_profile": "JSON string (optional)"
}
```

**Response**
```json
{
  "learning_path": [...],
  "agent_metadata": {},
  "adaptation": { "status": "applied | skipped", "reason": "string" }
}
```

**Display**
- While in-flight: show an info banner ("Learning path update in progress...").
- If `adaptation.status === "applied"`: show a toast ("Learning path adapted automatically") and reload the path.

---

### 4.3 Get Goal Runtime State — `GET /goal-runtime-state/{user_id}?goal_id={goal_id}`

Called on page load to get live session lock/mastery state from the backend.

**Frontend inputs** — none (automatic).

**Response**
```json
{
  "sessions": [
    {
      "is_locked": false,
      "is_mastered": false,
      "mastery_score": null,
      "mastery_threshold": 70
    }
  ],
  "adaptation": { "suggested": false }
}
```

**Display** — used to override session card lock/mastery display; not shown directly.

---

### 4.4 Post Session Activity — `POST /session-activity`

Called when a session is started (`event_type: "start"`), ended (`"end"`), or as a heartbeat (`"heartbeat"`).

**Frontend inputs** — none (automatic, triggered by navigation/timers).

**Request body**
```json
{
  "user_id": "string",
  "goal_id": 1,
  "session_index": 0,
  "event_type": "start | end | heartbeat",
  "event_time": "ISO datetime string (optional)"
}
```

**Response** (heartbeat only may contain)
```json
{
  "trigger": { "show": true, "message": "Motivational message text" }
}
```

**Display** — if `trigger.show === true`, show the `trigger.message` as a toast notification.

---

### 4.5 Update Goal — `PATCH /goals/{user_id}/{goal_id}`

Called after the learning path is generated or adapted to persist changes.

**Frontend inputs** — none (automatic).

**Request body** — partial update, e.g.:
```json
{ "learning_path": [...], "plan_agent_metadata": {} }
```

**Response** — updated goal object (no direct UI display needed).

---

## 5. Learning Session (Knowledge Document)

### Flow overview
When a user opens a session, the system fetches or generates learning content (document + quizzes). The user reads through paginated sections, then takes a quiz. After passing, they can mark the session complete.

---

### 5.1 Get Cached Learning Content — `GET /learning-content/{user_id}/{goal_id}/{session_index}`

Called first on session open to check for existing generated content.

**Frontend inputs** — none (automatic).

**Response** — same shape as the Generate Learning Content response (section 5.2). If 404/empty, fall through to generation.

---

### 5.2 Generate Learning Content — `POST /generate-learning-content`

Called if no cached content exists.

**Frontend inputs** — none (automatic).

**Request body**
```json
{
  "learner_profile": "JSON string",
  "learning_path": "JSON string of full path array",
  "learning_session": "JSON string of current session object",
  "use_search": true,
  "allow_parallel": true,
  "with_quiz": true,
  "goal_context": {},
  "llm_type": "gpt4o",
  "method_name": "ami",
  "user_id": "string",
  "goal_id": 1,
  "session_index": 0
}
```

**Response**
```json
{
  "learning_content": {
    "document": "full markdown string",
    "content_format": "standard | audio_enhanced | visual_enhanced",
    "audio_url": "path/to/audio.mp3 (optional)",
    "audio_mode": "narration_optional | host_expert (optional)",
    "sources_used": [
      { "title": "string", "url": "string", "source_type": "string" }
    ],
    "view_model": {
      "sections": [
        {
          "title": "string",
          "anchor": "string",
          "level": 2,
          "markdown": "section markdown content"
        }
      ],
      "references": [
        { "index": 1, "label": "Author et al. (2024). Title. URL." }
      ]
    },
    "quizzes": {
      "single_choice_questions": [
        {
          "question": "string",
          "options": ["A", "B", "C", "D"],
          "correct_option": 0,
          "explanation": "string"
        }
      ],
      "multiple_choice_questions": [
        {
          "question": "string",
          "options": ["A", "B", "C"],
          "correct_options": [0, 2],
          "explanation": "string"
        }
      ],
      "true_false_questions": [
        {
          "question": "string",
          "correct_answer": true,
          "explanation": "string"
        }
      ],
      "short_answer_questions": [
        {
          "question": "string",
          "expected_answer": "string",
          "explanation": "string"
        }
      ],
      "open_ended_questions": [
        {
          "question": "string",
          "rubric": "string",
          "example_answer": "string"
        }
      ]
    }
  }
}
```

**Display**
- Show a spinner ("Generating personalized learning content...") while in-flight.
- **Content format badges:**
  - `audio_enhanced`: show an info banner ("🎧 Optional narrated audio available" or "🎙️ Host-expert audio") + `<audio>` player.
  - `visual_enhanced`: show an info banner ("📊 Visual content included").
- **Document sections** (paginated by `view_model.sections`):
  - Render each section's `markdown` as rich markdown (support headings, code blocks, bold, images, etc.).
  - Sidebar/TOC: level-2 headings as navigation buttons; level-3 headings as anchor links.
  - "Previous Page" / "Next Page" buttons at the bottom.
  - Inline citation tooltips where `[N]` appears in markdown, linking to `sources_used[N]`.
  - References listed in a collapsible section at the bottom of the last page.
- Quiz renders only after the user reaches the last section.

---

### 5.3 Delete (Regenerate) Learning Content — `DELETE /learning-content/{user_id}/{goal_id}/{session_index}`

Called when the user clicks "Regenerate".

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Regenerate" button | `<button>` (secondary) | Available in header and at bottom |

**Response** — simple acknowledgement; no display needed.

**Display** — clear local content cache and re-trigger generation flow (section 5.2).

---

### 5.4 Quiz UI (no API call)

After the last document page, render the quiz:

| Question type | Input element |
|---|---|
| Single choice | Radio group |
| Multiple choice | Checkboxes |
| True/False | Radio group ("True" / "False") |
| Short answer | Single-line text input |
| Open-ended | Multi-line textarea (height ~150px) |

All inputs are disabled once the quiz is submitted.

---

### 5.5 Evaluate Mastery — `POST /evaluate-mastery`

Called when the user clicks "Submit Quiz".

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Submit Quiz" button | `<button>` (primary) | Active only when at least one answer is provided |

**Request body**
```json
{
  "user_id": "string",
  "goal_id": 1,
  "session_index": 0,
  "quiz_answers": {
    "single_choice_questions": ["A", null, "C"],
    "multiple_choice_questions": [["A", "C"]],
    "true_false_questions": ["True"],
    "short_answer_questions": ["user text"],
    "open_ended_questions": ["user essay"]
  }
}
```

**Response**
```json
{
  "score_percentage": 80.0,
  "is_mastered": true,
  "threshold": 70,
  "short_answer_feedback": [
    { "is_correct": true, "feedback": "Good explanation." }
  ],
  "open_ended_feedback": [
    {
      "solo_level": "relational | extended_abstract | multistructural | unistructural | prestructural",
      "score": 0.85,
      "feedback": "string"
    }
  ]
}
```

**Display after submission:**
- If `is_mastered`: green success message with score and threshold; unlock "Complete Session" button.
- If not mastered: yellow warning with score and required threshold; show "Retake Quiz" button.
- Show explanations in a collapsible "View Explanations" section:
  - Single/multiple choice/T-F: correct answer + explanation text.
  - Short answer: expected answer, explanation, then AI feedback (✓ or ✗ with color).
  - Open-ended: rubric + example answer, then SOLO level badge (colored) + AI feedback.

**SOLO level colors:**
| Level | Color |
|---|---|
| prestructural | #FF4444 |
| unistructural | #FF8800 |
| multistructural | #DDAA00 |
| relational | #2288FF |
| extended_abstract | #22CC66 |

---

### 5.6 Complete Session — `POST /complete-session`

Called when "Complete Session" is clicked (only enabled after mastery for linear sessions).

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Complete Session" button | `<button>` (primary) | Disabled until mastery achieved (linear mode) |

**Request body**
```json
{
  "user_id": "string",
  "goal_id": 1,
  "session_index": 0,
  "llm_type": "gpt4o",
  "method_name": "ami",
  "session_end_time": "ISO datetime string (optional)"
}
```

**Response**
```json
{
  "goal": { ...updated goal object... }
}
```

**Display**
- Show a spinner ("Updating learner profile...") while in-flight.
- On success: update the local goal object, navigate back to Learning Path.

---

### 5.7 Submit Content Feedback — `POST /submit-content-feedback`

Called when the user submits the session feedback form.

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Clarity of Content | Star rating (1–5) | Required |
| Relevance to Goals | Star rating (1–5) | Required |
| Depth of Content | Star rating (1–5) | Required |
| Engagement Level | Emoji/face rating | Required |
| Additional Comments | `<textarea>` | Optional, max 500 chars |
| "Submit Feedback" button | `<button>` | Submits the form |

**Request body**
```json
{
  "user_id": "string",
  "goal_id": 1,
  "feedback": {
    "clarity": 4,
    "relevance": 5,
    "depth": 3,
    "engagement": 2,
    "additional_comments": "string"
  },
  "llm_type": "gpt4o",
  "method_name": "ami"
}
```

**Response**
```json
{ "goal": { ...updated goal object... } }
```

**Display**
- On success: show a success message ("Thank you for your feedback!") and update goal state.

---

## 6. Goal Management

### Flow overview
Users can add new goals, edit or delete existing ones, and switch the active goal.

---

### 6.1 List Goals — `GET /goals/{user_id}`

Called on page load.

**Response**
```json
{
  "goals": [
    {
      "id": 1,
      "learning_goal": "string",
      "skill_gaps": [],
      "learning_path": [],
      "learner_profile": {},
      "is_deleted": false,
      "is_completed": false
    }
  ]
}
```

**Display**
- Render each non-deleted goal as a card showing:
  - `goal_display_name` (from `learner_profile.goal_display_name`) or fallback "Goal N".
  - `learning_goal` text.
  - Overall progress bar (derived from `learning_path` sessions marked `if_learned`).
  - Metrics: Total / Mastered / In-progress skill counts.
  - "Set as Active Goal" / "Current Active Goal" button.
  - "Edit" and "Delete" buttons.

---

### 6.2 Delete Goal — `DELETE /goals/{user_id}/{goal_id}`

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Delete" button | `<button>` (destructive) | Per-goal card |

**Response** — acknowledgement; update local list by setting `is_deleted: true`.

---

### 6.3 Update Goal — `PATCH /goals/{user_id}/{goal_id}`

Used when editing a goal's text.

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Goal text area | `<textarea>` | Editable when "Edit" is clicked |
| "Save" button | `<button>` | Saves changes |

**Request body** — partial, e.g. `{ "learning_goal": "new text" }`.

---

### 6.4 Add Goal flow

Adding a new goal triggers the same **Skill Gap** flow (section 3) inside a modal dialog, then creates the goal (section 3.7).

---

## 7. Learner Profile

### Flow overview
Displays the AI-generated learner profile (FSLSM dimensions, cognitive status, behavioral patterns) and allows the user to submit feedback to update learning preferences.

---

### 7.1 Get Learner Profile — `GET /profile/{user_id}?goal_id={goal_id}`

Called as a fallback if the in-memory profile is missing.

**Response**
```json
{ "learner_profile": { ...profile object... } }
```

**Display** — populates the profile view below.

---

### 7.2 Get Behavioral Metrics — `GET /behavioral-metrics/{user_id}?goal_id={goal_id}`

Called on profile page load to show real engagement data.

**Response** (`BehavioralMetricsResponse`)
```json
{
  "user_id": "string",
  "goal_id": 1,
  "sessions_completed": 3,
  "total_sessions_in_path": 8,
  "sessions_learned": 3,
  "avg_session_duration_sec": 900.0,
  "total_learning_time_sec": 2700.0,
  "motivational_triggers_count": 2,
  "mastery_history": [0.6, 0.75, 0.9],
  "latest_mastery_rate": 0.9
}
```

**Display**
- **Session Completion**: progress bar `sessions_learned / total_sessions_in_path` + caption.
- **Session Duration & Engagement**: three metric tiles (Sessions Completed, Avg Duration, Total Learning Time).
- **Motivational Triggers**: caption with trigger count.
- **Mastery Progress**: progress bar for `latest_mastery_rate` + caption with history sample count.
- If no data yet: show placeholder info messages.

---

### 7.3 Profile view sections

All data comes from the stored `learner_profile` object:

| Section | Data source | Display |
|---|---|---|
| Learner Information | `learner_profile.learner_information` | Plain text block |
| Learning Goal | `learner_profile.learning_goal` | Plain text block |
| Cognitive Status | `learner_profile.cognitive_status` | Progress bar + skill lists |
| Learning Preferences | `learner_profile.learning_preferences.fslsm_dimensions` | Four read-only sliders (−1 to +1) with left/right labels: Active↔Reflective, Sensing↔Intuitive, Visual↔Verbal, Sequential↔Global |
| Fairness banners | `goal.profile_fairness` | Info + optional warning banners (see section 3.6 display) |

---

### 7.4 Update Learning Preferences — `POST /update-learning-preferences`

Called when the user submits the "Update Profile" form.

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Agreement rating | Star rating (1–5) | Required |
| Suggestions text area | `<textarea>` | Required |
| Optional PDF upload | `<input type="file" accept=".pdf">` | Supplements profile with additional info |
| "Update Profile" button | `<button>` (primary) | Submits the form |

**Request body**
```json
{
  "learner_profile": "JSON string of current profile",
  "learner_interactions": "JSON string of feedback data",
  "learner_information": "string (optional)",
  "llm_type": "gpt4o",
  "method_name": "ami",
  "user_id": "string",
  "goal_id": 1
}
```

**Response**
```json
{ "learner_profile": { ...updated profile... } }
```

**Display**
- Show a spinner ("Updating your profile...") while in-flight.
- On success: show a toast ("Successfully updated your profile!") and refresh the profile view.

---

### 7.5 Delete User Data (Restart Onboarding) — `DELETE /user-data/{user_id}`

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| "Restart Onboarding" button | `<button>` | Opens confirmation dialog |
| Confirmation dialog | Modal | "Confirm" / "Cancel" |

**Display**
- On success: clear all local state, redirect to Onboarding while keeping the user logged in.

---

## 8. Dashboard / Analytics

### Flow overview
Shows learning progress charts and skill proficiency radar.

---

### 8.1 Get Dashboard Metrics — `GET /dashboard-metrics/{user_id}?goal_id={goal_id}`

Called on page load.

**Response**
```json
{
  "overall_progress": 37.5,
  "skill_radar": {
    "labels": ["Python", "SQL", "ML"],
    "current_levels": [1, 2, 0],
    "required_levels": [3, 3, 2],
    "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"]
  },
  "session_time_series": [
    { "session_id": "Session 1", "time_spent_min": 15.0 }
  ],
  "mastery_time_series": [
    { "sample_index": 0, "mastery_rate": 0.0 },
    { "sample_index": 1, "mastery_rate": 0.5 }
  ]
}
```

**Display**
- **Overall Progress**: progress bar + percentage label.
- **Skill Radar Chart**: polar/radar chart (Plotly or Recharts) with two series:
  - "Current Proficiency Level" (filled area).
  - "Required Proficiency Level" (pink filled area).
  - Radial axis ticks labeled with `skill_levels` names.
- **Session Learning Timeseries**: bar chart with Session on x-axis and Time (minutes) on y-axis.
- **Mastery Timeseries**: line chart with Time (sample index × 10) on x-axis and Mastery Rate on y-axis.

---

## 9. AI Tutor Chat

### 9.1 Chat with Tutor — `POST /chat-with-tutor`

**Frontend inputs**
| Element | Type | Notes |
|---|---|---|
| Chat message input | `<input type="text">` or `<textarea>` | User's question |
| "Send" button | `<button>` | Submits the message |
| Chat history display | Message list | Shows previous exchanges |

**Request body**
```json
{
  "messages": "JSON string of message array [{ role, content }]",
  "learner_profile": "JSON string of learner profile",
  "llm_type": "gpt4o",
  "method_name": "ami"
}
```

**Response**
```json
{ "response": "AI tutor reply string" }
```

**Display**
- Show the response as a new assistant message in the chat history.
- Render the reply as markdown (the tutor response may include code blocks, lists, etc.).
- Show a typing indicator while the request is in-flight.

---

## 10. Shared / Utility Endpoints

### 10.1 Get App Config — `GET /config`

Called once on app boot.

**Response**
```json
{
  "skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
  "default_session_count": 8,
  "default_llm_type": "gpt4o",
  "default_method_name": "ami",
  "motivational_trigger_interval_secs": 180,
  "max_refinement_iterations": 5,
  "fslsm_thresholds": {
    "perception": { "low_threshold": -0.3, "high_threshold": 0.3, "low_label": "...", "high_label": "...", "neutral_label": "..." },
    "understanding": { ... },
    "processing": { ... },
    "input": { ... }
  }
}
```

**Display** — stored globally; drives skill level dropdowns, session count defaults, and FSLSM label descriptions.

---

### 10.2 List LLM Models — `GET /list-llm-models`

Called in settings/debug sidebar.

**Response**
```json
{ "models": ["gpt4o", "deepseek", "ollama"] }
```

**Display** — populates a model selector dropdown (admin/debug feature).

---

### 10.3 Get Quiz Mix — `GET /quiz-mix/{user_id}?goal_id={goal_id}&session_index={index}`

Called before quiz generation to determine question type counts.

**Response**
```json
{
  "single_choice_count": 3,
  "multiple_choice_count": 1,
  "true_false_count": 1,
  "short_answer_count": 1,
  "open_ended_count": 0
}
```

**Display** — used internally to configure quiz generation; no direct UI.

---

### 10.4 Get Session Mastery Status — `GET /session-mastery-status/{user_id}?goal_id={goal_id}`

Called to restore mastery state across page reloads.

**Response** — map of `session_index → { is_mastered, score, threshold }`.

**Display** — used to restore quiz state (disable re-submission if already mastered).

---

### 10.5 Sync Profile — `POST /sync-profile/{user_id}/{goal_id}`

Called after updating learning preferences to propagate FSLSM/mastery data to other goals.

**Response**
```json
{ "learner_profile": { ...updated profile... } }
```

**Display** — no direct UI; updates local profile cache.

---

### 10.6 Save Learner Profile — `PUT /profile/{user_id}/{goal_id}`

Persists a profile without triggering an LLM call.

**Request body**
```json
{ "learner_profile": { ...profile object... } }
```

**Response** — 200 OK; no display needed.

---

## Appendix: URL / Method Summary

| Key | Method | Path |
|---|---|---|
| auth_register | POST | `/auth/register` |
| auth_login | POST | `/auth/login` |
| auth_delete_user | DELETE | `/auth/user` |
| list_goals | GET | `/goals/{user_id}` |
| create_goal | POST | `/goals/{user_id}` |
| update_goal | PATCH | `/goals/{user_id}/{goal_id}` |
| delete_goal | DELETE | `/goals/{user_id}/{goal_id}` |
| get_goal_runtime_state | GET | `/goal-runtime-state/{user_id}?goal_id={goal_id}` |
| get_personas | GET | `/personas` |
| extract_pdf_text | POST | `/extract-pdf-text` (multipart) |
| refine_goal | POST | `/refine-learning-goal` |
| identify_skill_gap | POST | `/identify-skill-gap-with-info` |
| audit_skill_gap_bias | POST | `/audit-skill-gap-bias` |
| create_profile | POST | `/create-learner-profile-with-info` |
| validate_profile_fairness | POST | `/validate-profile-fairness` |
| update_profile | POST | `/update-learner-profile` |
| update_cognitive_status | POST | `/update-cognitive-status` |
| update_learning_preferences | POST | `/update-learning-preferences` |
| get_learner_profile | GET | `/profile/{user_id}?goal_id={goal_id}` |
| save_learner_profile | PUT | `/profile/{user_id}/{goal_id}` |
| sync_profile | POST | `/sync-profile/{user_id}/{goal_id}` |
| schedule_path | POST | `/schedule-learning-path` |
| schedule_path_agentic | POST | `/schedule-learning-path-agentic` |
| adapt_path | POST | `/adapt-learning-path` |
| get_learning_content | GET | `/learning-content/{user_id}/{goal_id}/{session_index}` |
| generate_learning_content | POST | `/generate-learning-content` |
| delete_learning_content | DELETE | `/learning-content/{user_id}/{goal_id}/{session_index}` |
| session_activity | POST | `/session-activity` |
| complete_session | POST | `/complete-session` |
| evaluate_mastery | POST | `/evaluate-mastery` |
| submit_content_feedback | POST | `/submit-content-feedback` |
| get_session_mastery_status | GET | `/session-mastery-status/{user_id}?goal_id={goal_id}` |
| get_quiz_mix | GET | `/quiz-mix/{user_id}?goal_id={goal_id}&session_index={index}` |
| get_dashboard_metrics | GET | `/dashboard-metrics/{user_id}?goal_id={goal_id}` |
| get_behavioral_metrics | GET | `/behavioral-metrics/{user_id}?goal_id={goal_id}` |
| chat_with_tutor | POST | `/chat-with-tutor` |
| delete_user_data | DELETE | `/user-data/{user_id}` |
| get_app_config | GET | `/config` |
| list_llm_models | GET | `/list-llm-models` |
