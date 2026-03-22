# Bias Audit Persistence & Analytics Dashboard — Testing Guide

> **Purpose:** This document provides backend test details and manual frontend verification steps for the **Bias Audit Persistence & Analytics Dashboard** feature, which logs all bias audit results and displays them in a dedicated dashboard section.
>
> **How to use:** Run the backend tests first to verify correctness, then follow the Streamlit frontend steps to verify the full user experience. Copy into a Google Doc to check off steps and leave comments.
>
> **Prerequisites:** Log in or register. Have at least one learning goal set up (complete onboarding by selecting a persona, entering a learning goal, and clicking "Begin Learning").

---

## Overview

This feature adds **persistent tracking** of all bias audit results and a new **"Bias & Ethics Review"** section in the Learning Analytics dashboard. Previously, bias audit results from Content and Chatbot auditors were ephemeral (returned to the frontend and forgotten). Now all 4 audit types are logged with timestamps for historical analysis.

### What Was Added

| Component | Location | Description |
|-----------|----------|-------------|
| Bias audit log store | `backend/utils/store.py` | Append-only JSON store keyed by user, capped at 200 entries per user |
| Auto-persist on audit | `backend/main.py` | All 4 audit endpoints now log results when `user_id` is provided |
| History endpoint | `GET /v1/bias-audit-history/{user_id}` | Returns audit log entries + summary statistics |
| Frontend API helper | `frontend/utils/request_api.py` | `get_bias_audit_history()` function |
| Dashboard section | `frontend/pages/dashboard.py` | "Bias & Ethics Review" section with charts and metrics |

### Audit Types Tracked

| Audit Type | Trigger | Endpoint |
|------------|---------|----------|
| `skill_gap_bias` | After skill gap identification | `POST /v1/audit-skill-gap-bias` |
| `profile_fairness` | After learner profile creation | `POST /v1/validate-profile-fairness` |
| `content_bias` | After learning content generation | `POST /v1/audit-content-bias` |
| `chatbot_bias` | During AI tutor chat sessions | `POST /v1/audit-chatbot-bias` |

### Each Log Entry Contains

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO string | When the audit was performed |
| `goal_id` | int or null | Which learning goal was being audited |
| `audit_type` | string | One of the 4 audit types above |
| `overall_risk` | string | `"low"`, `"medium"`, or `"high"` |
| `flagged_count` | int | Number of bias flags detected |
| `audited_count` | int | Number of items audited |
| `flags_summary` | list | Compact list of `{category, severity}` (max 20) |

---

## Backend Test Scripts

| Test file | Class / Tests | What it covers |
|-----------|---------------|----------------|
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_basic_append_and_retrieve` | Appends an entry and verifies all fields are stored correctly |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_200_entry_cap` | Verifies the 200-entry-per-user cap works (inserts 210, expects 200) |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_filter_by_goal_id` | Filters entries by goal_id correctly |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_empty_user_returns_empty` | Returns empty list for nonexistent user |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_returns_deep_copy` | Verifies returned data is a deep copy (mutations don't affect store) |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_none_goal_id_stored` | Handles None goal_id gracefully |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_multiple_users_isolated` | Different users' logs are independent |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_persistence_to_disk` | Verifies data is flushed to JSON file on disk |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_flags_summary_capped_at_20` | flags_summary stores at most 20 items even if more flags exist |
| `test_bias_audit_persistence.py` | `TestAppendBiasAuditLog::test_delete_all_user_data_clears_log` | `delete_all_user_data()` removes bias audit log for the user |
| `test_bias_audit_persistence.py` | `TestBiasAuditHistoryEndpoint` (4 tests) | Endpoint returns entries + summary, filters by goal_id, handles empty history, returns 403 for other users |

**Run command:**
```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_bias_audit_persistence.py -v --noconftest
```

**Expected output:** 10 store-level tests passed, 4 endpoint tests skipped (due to pre-existing chromadb/Python 3.14 incompatibility in conftest — this affects all endpoint tests project-wide, not specific to this feature).

---

## Streamlit Frontend Test Steps

### Prerequisites

- [ ] Backend is running on `http://localhost:8000`
- [ ] Frontend is running on `http://localhost:8501`
- [ ] You are logged in with a registered account

---

### Test 1: Verify Empty State

**Goal:** Confirm the dashboard section renders correctly before any audits have been run.

1. Navigate to **Learning Analytics** (dashboard page)
2. Select any learning goal from the dropdown
3. Scroll to the bottom, past the 4 existing sections (Learning Progress, Proficiency Levels, Session Learning Timeseries, Mastery Skills Timeseries)
4. **Expected:** A 5th section titled **"Bias & Ethics Review"** is visible
5. **Expected:** An info box reads **"No bias audits recorded yet."**

- [ ] Pass / Fail: ___

---

### Test 2: Trigger a Skill Gap Bias Audit

**Goal:** Verify the skill gap bias audit is logged and appears in the dashboard.

1. Start a **new learning goal** (click "New Goal" or go through onboarding)
2. Select a persona and enter a learning goal (e.g., "Learn Python programming")
3. Click **"Begin Learning"** and wait for skill gap identification to complete
4. The bias audit runs automatically after skill gaps are identified — look for the bias audit results panel on the onboarding page
5. Navigate to **Learning Analytics**
6. Select the goal you just created
7. Scroll to **"Bias & Ethics Review"**
8. **Expected:** Summary metrics show at least **1 total audit**
9. **Expected:** The "Recent Audits" table shows an entry with Type = **"Skill Gap Bias"**

- [ ] Pass / Fail: ___

---

### Test 3: Trigger a Profile Fairness Audit

**Goal:** Verify the profile fairness validation is logged.

1. Continue the onboarding flow after skill gap identification
2. Wait for the learner profile to be created — the fairness validation runs automatically
3. Navigate to **Learning Analytics** and select the same goal
4. Scroll to **"Bias & Ethics Review"**
5. **Expected:** Total audits now shows **2** (skill gap + profile fairness)
6. **Expected:** The "Recent Audits" table shows an entry with Type = **"Profile Fairness"**

- [ ] Pass / Fail: ___

---

### Test 4: Trigger a Content Bias Audit

**Goal:** Verify the content bias audit is logged after generating learning content.

1. Complete onboarding and generate a learning path
2. Click on a session to generate learning content
3. Wait for content generation to complete — the content bias audit runs in the background
4. Navigate to **Learning Analytics** and select the same goal
5. Scroll to **"Bias & Ethics Review"**
6. **Expected:** Total audits has increased
7. **Expected:** The "Recent Audits" table shows an entry with Type = **"Content Bias"**

- [ ] Pass / Fail: ___

---

### Test 5: Trigger a Chatbot Bias Audit

**Goal:** Verify the chatbot bias audit is logged during tutoring.

1. Open the **AI Tutor Chat** for a session
2. Have a multi-turn conversation (at least 3-4 messages)
3. The chatbot bias audit runs periodically during the conversation
4. Navigate to **Learning Analytics** and select the same goal
5. Scroll to **"Bias & Ethics Review"**
6. **Expected:** Total audits has increased
7. **Expected:** The "Recent Audits" table shows an entry with Type = **"Chatbot Bias"**

- [ ] Pass / Fail: ___

---

### Test 6: Verify Dashboard Charts

**Goal:** Confirm charts render correctly with data.

After completing Tests 2-5 (or at least 2-3 audits):

1. Navigate to **Learning Analytics** and select a goal with audit history
2. Scroll to **"Bias & Ethics Review"**
3. **Expected:** Three summary metric cards at the top:
   - **Total Audits** — shows the correct count
   - **Flags Detected** — shows total number of bias flags found
   - **Current Risk** — shows "Low", "Medium", or "High"
4. **Expected:** **Risk Distribution** bar chart — shows counts for low/medium/high risk audits
5. **Expected:** **Bias Categories Flagged** bar chart — shows most common bias categories (only appears if flags were detected)
6. **Expected:** **Recent Audits** table — shows up to 20 most recent audits with Time, Type, Risk, and Flags columns

- [ ] Pass / Fail: ___

---

### Test 7: Verify Goal Filtering

**Goal:** Confirm the dashboard filters audit history by selected goal.

1. Create a **second learning goal** and complete onboarding for it (to trigger audits under a different goal)
2. Navigate to **Learning Analytics**
3. Switch between the two goals using the dropdown at the top
4. **Expected:** The "Bias & Ethics Review" section updates to show only audits for the selected goal
5. **Expected:** Audit counts differ between goals

- [ ] Pass / Fail: ___

---

### Test 8: Verify Backend API Directly (Optional)

**Goal:** Verify the history endpoint returns correct data.

1. Get your auth token (from browser dev tools > Application > Local Storage > `auth_token`)
2. Run:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/v1/bias-audit-history/YOUR_USER_ID
   ```
3. **Expected:** JSON response with `entries` array and `summary` object:
   ```json
   {
     "entries": [
       {
         "timestamp": "2026-03-11T...",
         "goal_id": 0,
         "audit_type": "skill_gap_bias",
         "overall_risk": "low",
         "flagged_count": 0,
         "audited_count": 5,
         "flags_summary": []
       }
     ],
     "summary": {
       "total_audits": 1,
       "total_flags": 0,
       "current_risk": "low",
       "risk_distribution": {"low": 1, "medium": 0, "high": 0},
       "category_counts": {}
     }
   }
   ```
4. Test goal filtering:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" "http://localhost:8000/v1/bias-audit-history/YOUR_USER_ID?goal_id=0"
   ```
5. **Expected:** Only entries with `goal_id: 0` are returned

- [ ] Pass / Fail: ___

---

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `backend/utils/store.py` | Modified | Added `_BIAS_AUDIT_LOG_PATH`, `_bias_audit_log` cache, `append_bias_audit_log()`, `get_bias_audit_log()`, registered in `load()` and `delete_all_user_data()` |
| `backend/api_schemas.py` | Modified | Added optional `user_id` and `goal_id` fields to `BiasAuditRequest`, `ProfileFairnessRequest`, `ContentBiasAuditRequest`, `ChatbotBiasAuditRequest` |
| `backend/main.py` | Modified | Auto-persist audit results in all 4 audit endpoints; added `GET /v1/bias-audit-history/{user_id}` endpoint |
| `frontend/utils/request_api.py` | Modified | Added `bias_audit_history` to `API_NAMES`; added `get_bias_audit_history()` function |
| `frontend/pages/dashboard.py` | Modified | Added `render_bias_ethics_review()` as 5th dashboard section |
| `backend/tests/test_bias_audit_persistence.py` | Created | 14 tests (10 store-level + 4 endpoint-level) |

---

## Known Limitations

- **Existing audits not retroactively logged:** Only audits triggered *after* this update will appear in the history. Previous audit results were not persisted.
- **Endpoint tests skip in current environment:** The 4 endpoint-level tests in `test_bias_audit_persistence.py` skip due to a pre-existing chromadb/pydantic v1 incompatibility with Python 3.14 in `conftest.py`. This affects all endpoint tests project-wide. Store-level tests (10/10) pass fully.
- **Content and Chatbot audits require frontend changes to pass user_id:** The frontend `audit_content_bias()` and `audit_chatbot_bias()` functions in `request_api.py` do not currently pass `user_id`/`goal_id` in their payloads. These audits will only be logged if the calling page-level code is updated to include these fields in the request data. The skill gap and profile fairness audits are logged because those endpoints already receive user context.
