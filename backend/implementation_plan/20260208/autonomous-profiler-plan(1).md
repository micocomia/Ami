# Plan: Autonomous Adaptive Learner Profiling Agent

## Context

The adaptive learner profiler currently only updates when the user explicitly triggers it (submitting content feedback, clicking "Complete Session", or updating via the profile page). Rich interaction data from chat sessions, quiz answers, time spent, and navigation patterns is generated but never fed to the profiler. The goal is to instrument these signals, pipe them through the existing `/events/log` system, and add backend logic that autonomously decides when to trigger a profile update — making the agent a "true" autonomous agent.

## Approach

**Event-driven architecture**: Instrument frontend interactions to log events via the existing `/events/log` endpoint, then add trigger logic to the backend that evaluates accumulated events and signals the frontend when a profile update is warranted.

## Changes

### Step 1: Frontend event logging helper — `frontend/utils/request_api.py`

Add two new functions:
- `log_event(event_type, payload)` — fire-and-forget POST to `/events/log`, checks response for `should_update` flag, and if true calls `_trigger_auto_update()`
- `_trigger_auto_update(user_id)` — calls `/profile/auto-update` and writes the updated profile back to session state

### Step 2: Backend trigger logic — `backend/main.py`

- Add `should_trigger_update(user_id)` function that counts events since the last `_profile_updated` marker event. Triggers an update when either:
  - 3+ significant events (`quiz_answer`, `session_completed`, `content_feedback`, `content_regeneration`)
  - 10+ total events of any kind
- Modify `/events/log` response to include `"should_update": bool`
- Modify `/profile/auto-update` to append a `_profile_updated` marker event after successful updates

### Step 3: Enhanced profiler prompts — `backend/modules/adaptive_learner_modeling/prompts.py`

Extend the update task prompt and chain-of-thought with guidance on interpreting each new event type:
- `quiz_answer` → update cognitive_status (skill mastery)
- `chat_exchange` → infer understanding gaps, inform preferences
- `content_feedback` → adjust FSLSM dimensions based on ratings
- `content_regeneration` → signal content/style mismatch
- `section_navigation` → infer sequential vs. global learning style
- `session_completed` → update behavioral_patterns with time data

Include guardrails: small FSLSM adjustments (0.1-0.2), no fabricated changes, pattern-based reasoning.

### Step 4: Instrument frontend interactions

**4a. Quiz results** — `frontend/pages/knowledge_document.py` `render_questions()`
- Log `quiz_answer` event after each answer (all 4 question types: single choice, multiple choice, true/false, short answer)
- Payload: `question_type`, `question`, `is_correct`, `session_id`, `goal_id`

**4b. Chat exchanges** — `frontend/components/chatbot.py` `ask_autor_chatbot()`
- Log `chat_exchange` after tutor response
- Payload: `user_question`, `tutor_response_preview` (truncated to 300 chars), `message_count`, `goal_id`

**4c. Content regeneration** — `frontend/pages/knowledge_document.py` (2 Regenerate buttons)
- Log `content_regeneration` at both regenerate button clicks
- Payload: `session_id`, `goal_id`

**4d. Section navigation** — `frontend/pages/knowledge_document.py` `render_document_content_by_section()`
- Log `section_navigation` on Next Page, Previous Page, and TOC sidebar clicks
- Payload: `action`, `from_page`, `to_page`, `total_pages`, `session_id`, `goal_id`

**4e. Content feedback** — `frontend/pages/knowledge_document.py` `render_content_feedback_form()`
- Log `content_feedback` on feedback form submit
- Payload: `clarity`, `relevance`, `depth`, `engagement`, `additional_comments`, `session_id`, `goal_id`

**4f. Session completion** — `frontend/pages/knowledge_document.py` `update_learner_profile_with_feedback()`
- Log `session_completed` with time spent data from `session_learning_times`
- Payload: `session_id`, `goal_id`, `time_spent_seconds`, `feedback_data`

## Files Modified

| File | Change |
|------|--------|
| `frontend/utils/request_api.py` | Add `log_event()` and `_trigger_auto_update()` |
| `backend/main.py` | Add `should_trigger_update()`, modify `/events/log` response, add marker event to `/profile/auto-update` |
| `backend/modules/adaptive_learner_modeling/prompts.py` | Extend update prompt + CoT with event interpretation guidance |
| `frontend/pages/knowledge_document.py` | Instrument quiz, navigation, regeneration, feedback, completion |
| `frontend/components/chatbot.py` | Instrument chat exchange events |

## Data Flow

```
User action (quiz/chat/navigate/regenerate/feedback)
  → Frontend: log_event() → POST /events/log
  → Backend: store event, evaluate should_trigger_update()
  → Response: { should_update: true/false }
  → [if true] Frontend: _trigger_auto_update() → POST /profile/auto-update
  → Backend: LLM processes all recent events using enhanced prompt
  → Updated profile written to PROFILE_STORE + frontend session state
  → _profile_updated marker appended to EVENT_STORE (resets trigger counter)
```

## Verification

1. Start backend and frontend locally
2. Go through a learning session, answer 3+ quiz questions
3. Check `GET /events/{user_id}` — should show `quiz_answer` events
4. After the 3rd quiz answer, the profile should auto-update (visible via `GET /profile/{user_id}` or refreshing the profile page)
5. Chat with tutor, verify `chat_exchange` events appear
6. Navigate sections back/forward, verify `section_navigation` events
7. Confirm the profile's cognitive_status, learning_preferences, and behavioral_patterns reflect the new signals
