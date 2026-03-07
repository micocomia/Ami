# Chatbot Bias Auditor — Testing Guide

> **Purpose:** This document provides backend test details and manual frontend verification steps for the **Chatbot Bias Auditor** module, which audits AI tutor chatbot responses for tone bias, language bias, stereotype bias, and cultural assumptions.
>
> **How to use:** Run the backend tests first to verify correctness, then follow the Streamlit frontend steps to verify the full user experience. Copy into a Google Doc to check off steps and leave comments.
>
> **Prerequisites:** Log in or register. Complete onboarding (select a persona, enter a learning goal, click "Begin Learning"). Wait for skill gap identification, then schedule a learning path. Navigate to any page where the "Ask Ami" chatbot button is available.

---

## Overview

The Chatbot Bias Auditor is a **post-processing layer** that runs automatically after each AI tutor response is generated. It does **not** block the user flow — if the audit endpoint fails, the chatbot continues working normally.

### What It Checks

| Check | Type | Description |
|-------|------|-------------|
| Tone bias detection | LLM | Flags condescending, patronizing, or assumption-laden responses not justified by learner proficiency |
| Language bias detection | LLM | Identifies gendered, ableist, or culturally insensitive language in tutor responses |
| Stereotype bias detection | LLM | Checks if explanation depth/style is influenced by demographic assumptions rather than assessed skill level |
| Cultural assumption detection | LLM | Flags examples or analogies that assume a specific cultural context |
| Biased language scanning | Deterministic | Keyword scanning for 15 known biased phrases (e.g., "mankind", "chairman", "suffers from") |
| Patronizing language scanning | Deterministic | Keyword scanning for 14 known patronizing phrases (e.g., "obviously", "this is easy", "surely you know") |

### Bias Categories

The auditor classifies flags into 4 categories:

| Category | Description |
|----------|-------------|
| `tone_bias` | Condescending, patronizing, or assumption-laden tone not justified by learner proficiency |
| `language_bias` | Gendered, ableist, or culturally insensitive language in responses |
| `stereotype_bias` | Explanation depth or style influenced by demographic assumptions rather than assessed skill |
| `cultural_assumption` | Examples or analogies that assume a specific cultural context |

### Biased Phrases Detected (Deterministic)

The deterministic scanner checks for 15 known biased phrases and suggests inclusive alternatives:

| Biased Phrase | Suggested Alternative |
|---------------|----------------------|
| mankind | humankind |
| manmade / man-made | artificial |
| chairman | chairperson |
| policeman | police officer |
| fireman | firefighter |
| stewardess | flight attendant |
| normal people | most people |
| suffers from | lives with |
| confined to a wheelchair | uses a wheelchair |
| the disabled | people with disabilities |
| the blind | people who are blind |
| the deaf | people who are deaf |
| third world | developing countries |
| primitive | traditional |

### Patronizing Phrases Detected (Deterministic)

The deterministic scanner also checks for 14 patronizing phrases:

| Patronizing Phrase |
|--------------------|
| as i'm sure you know |
| as i am sure you know |
| this is really simple |
| this is very simple |
| this is easy |
| this should be obvious |
| obviously |
| even you can |
| anyone can understand |
| it's not that hard |
| surely you know |
| you should already know |
| as a beginner you wouldn't |
| don't worry, it's simple |

---

## Backend Test Scripts

| Test file | Class / Tests | What it covers |
|-----------|---------------|----------------|
| `test_chatbot_bias_auditor.py` | `TestChatbotBiasAuditSchemas` (6 tests) | ChatbotBiasCategory enum values, ChatbotBiasSeverity enum values, ChatbotBiasFlag validation (valid flag, explanation word limit, suggestion word limit), ChatbotBiasAuditResult defaults |
| `test_chatbot_bias_auditor.py` | `TestBiasedLanguageCheck` (6 tests) | Deterministic `_check_biased_language`: detects "mankind", "chairman", "suffers from", clean content not flagged, case insensitive, correct category assigned |
| `test_chatbot_bias_auditor.py` | `TestPatronizingPhraseCheck` (5 tests) | Deterministic `_check_patronizing_language`: detects "obviously", "this is easy", "surely you know", clean content not flagged, correct medium severity assigned |
| `test_chatbot_bias_auditor.py` | `TestMessageCounting` (3 tests) | `_count_tutor_messages`: counts assistant markers, single response, paragraph-based counting |
| `test_chatbot_bias_auditor.py` | `TestChatbotBiasAuditorAgent` (6 tests, mocked LLM) | Clean responses return no flags, LLM bias flags detected, deterministic language flags promote risk, patronizing flags promote risk, ethical disclaimer present, combined LLM and deterministic flags |
| `test_chatbot_bias_auditor.py` | `TestAuditChatbotBiasWithLlm` (1 test) | Convenience function creates ChatbotBiasAuditor instance and returns dict |

**Run command:**
```bash
python -m pytest backend/tests/test_chatbot_bias_auditor.py -v
```

**Expected output:** 27 tests passed.

---

## Streamlit Frontend Test Steps

### Where the Chatbot Bias Audit Appears

The chatbot bias audit results are displayed inside the **"Ask Ami" chatbot dialog** (`components/chatbot.py`), below the tutor's response message.

**Relevant frontend files:**
- `frontend/components/chatbot_bias.py` — `render_chatbot_bias_banners(audit_result)` component
- `frontend/components/chatbot.py` — imports and calls `audit_chatbot_bias()` after each tutor response, renders bias banners
- `frontend/utils/request_api.py` — `audit_chatbot_bias()` API helper

---

### Test 1 — Clean Response (No Bias Flags)

> **Scenario:** Use a neutral, technical question.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding with any persona and a technical goal (e.g., "Learn Python data structures") | Goal created |
| 2 | Click the "Ask Ami" button to open the chatbot dialog | Chatbot dialog opens with greeting |
| 3 | Ask a neutral question (e.g., "Can you explain what a linked list is?") | Ami responds with a helpful explanation |
| 4 | Observe the chatbot dialog below the response | No warning banner. No bias audit expander visible |

---

### Test 2 — Bias Flags Detected (Warning Banner)

> **Scenario:** Tutor response contains biased elements flagged by the LLM.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open the chatbot and interact with Ami | Tutor responds |
| 2 | If the LLM detects bias in the tutor response | A **warning banner** (orange/yellow) appears: *"Moderate/High bias risk detected: X of Y messages flagged. Review the details below."* |
| 3 | Click the **"View chatbot bias audit details"** expander | Expander opens showing individual bias flags |
| 4 | Verify each bias flag shows | Message index, bias category (e.g., "tone_bias"), severity (low/medium/high), explanation, and suggestion |
| 5 | Verify severity icons | Low = yellow circle, Medium = orange circle, High = red circle |

> **Note:** Whether LLM-based bias flags appear depends on the response generated. The deterministic checks (Tests 3 & 4) are more reliably reproducible.

---

### Test 3 — Deterministic Language Bias Detection

> **Scenario:** Tutor response happens to contain known biased phrases.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Interact with Ami on a topic that may elicit responses with older terminology | Tutor responds |
| 2 | If the response contains any of the 15 tracked biased phrases (e.g., "mankind", "chairman") | The bias audit expander should contain a **"Language & Tone Warnings"** section with entries like: *"The phrase 'mankind' was detected in the tutor response. This may be considered non-inclusive language."* with a suggestion to use the inclusive alternative |
| 3 | If deterministic flags exist but LLM reported "low" risk | The overall risk is automatically promoted to **"medium"**, and a warning banner appears |

---

### Test 4 — Deterministic Patronizing Language Detection

> **Scenario:** Tutor response contains patronizing phrases.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Interact with Ami | Tutor responds |
| 2 | If the response contains any of the 14 patronizing phrases (e.g., "obviously", "this is easy") | The bias audit expander shows a **"Language & Tone Warnings"** entry with medium severity, explaining the patronizing phrase detected |
| 3 | Risk promotion | If LLM said "low" but patronizing phrases are found, overall risk is promoted to **"medium"** |

---

### Test 5 — Chatbot Bias Audit Does Not Block User Flow

> **Scenario:** Verify the audit is non-blocking.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Open the chatbot and send a message | Tutor responds normally |
| 2 | Regardless of bias audit result | The chatbot continues to work — user can send more messages, receive responses, and interact normally |
| 3 | If the chatbot bias audit endpoint is unavailable (e.g., backend error) | No crash. No error message visible to the user (error is silently caught). The chatbot still works |

---

### Test 6 — Chatbot Bias Details in Expander

> **Scenario:** Verify the full structure of the bias audit expander when flags exist.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger bias flags (see Tests 2-4) | Warning banner and expander are visible |
| 2 | Open the "View chatbot bias audit details" expander | Expander opens |
| 3 | Verify **Chatbot Bias Flags** section (if present) | Each flag shows: severity icon, **Message [index]** (bold), *bias category* (italic), (severity), explanation text, **Suggestion:** text |
| 4 | Verify **Language & Tone Warnings** section (if present) | Each flag shows: warning icon, explanation of the biased/patronizing phrase detected, **Suggestion:** how to improve |

---

## Dashboard Goal Label Test Steps

### Where the Goal Label Appears

The skill radar chart title on the **Learning Analytics** dashboard (`pages/dashboard.py`) now includes the learning goal name for clarity.

---

### Test 7 — Skill Radar Chart Shows Goal Name

> **Scenario:** Verify the chart title includes the goal name.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding with a learning goal (e.g., "Learn how to make pasta") | Goal created with skills |
| 2 | Navigate to the Learning Analytics dashboard | Dashboard loads with charts |
| 3 | Observe the skill radar chart title | Title shows: **"Proficiency Levels for Different Skills — Learn how to make pasta"** (includes the goal name) |
| 4 | If user has multiple goals, switch between them | The chart title updates to reflect the selected goal |

---

## Architecture Reference

```
Frontend                           Backend
────────                           ───────
Chatbot Dialog (Ask Ami)
  └─ ask_autor_chatbot()
       ├─ POST /chat-with-tutor  (existing)
       │    → returns tutor response
       └─ POST /audit-chatbot-bias  (chatbot bias audit)
            → takes tutor_responses + learner_information
            → returns ChatbotBiasAuditResult
                ├─ bias_flags[]
                ├─ deterministic_flags[]
                ├─ overall_bias_risk (low/medium/high)
                ├─ audited_message_count
                ├─ flagged_message_count
                └─ ethical_disclaimer
```

---

## Key Files

| File | Role |
|------|------|
| `backend/modules/ai_chatbot_tutor/schemas.py` | `ChatbotBiasCategory`, `ChatbotBiasSeverity`, `ChatbotBiasFlag`, `ChatbotBiasAuditResult` models |
| `backend/modules/ai_chatbot_tutor/agents/chatbot_bias_auditor.py` | `ChatbotBiasAuditor` agent with `audit_responses()` + deterministic `_check_biased_language()` and `_check_patronizing_language()` |
| `backend/modules/ai_chatbot_tutor/prompts/chatbot_bias_auditor.py` | System prompt and task prompt for the LLM |
| `backend/main.py` | `POST /audit-chatbot-bias` endpoint |
| `backend/api_schemas.py` | `ChatbotBiasAuditRequest` request schema |
| `backend/tests/test_chatbot_bias_auditor.py` | 27 unit tests |
| `frontend/components/chatbot_bias.py` | `render_chatbot_bias_banners()` banner component |
| `frontend/components/chatbot.py` | Imports and calls `audit_chatbot_bias()`, renders bias banners after tutor response |
| `frontend/utils/request_api.py` | `audit_chatbot_bias()` API helper |
| `frontend/pages/dashboard.py` | Updated skill radar chart title with goal name |
| `backend/implementation_plan/20260305/chatbot-bias-auditor-implementation-plan.md` | Full implementation plan |
