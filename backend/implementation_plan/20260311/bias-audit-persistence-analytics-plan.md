# Bias Audit Persistence & Analytics Dashboard — Implementation Plan

## Context

All 4 bias auditors (Skill Gap, Learner Profiler, Content Generator, Chatbot) are fully implemented, but audit results are only partially persisted:
- **Skill Gap bias audit** and **Profile Fairness** results are saved in `goals.json` (via goal creation/patching)
- **Content bias** and **Chatbot bias** audit results are ephemeral — returned to the frontend and forgotten

Without persistence, we cannot track bias patterns over time or show analytics. This plan adds:
1. A dedicated bias audit log store in the backend (append-only, timestamped)
2. A backend endpoint to retrieve bias audit history per user
3. A new "Bias & Ethics Review" section in the Learning Analytics dashboard

## Files to Modify

### 1. `backend/utils/store.py`
Add a new `bias_audit_log.json` persistence layer following the existing `append_mastery_history` pattern:
- New file path: `_BIAS_AUDIT_LOG_PATH = _DATA_DIR / "bias_audit_log.json"`
- New in-memory cache: `_bias_audit_log` keyed by `user_id`
- Functions:
  - `append_bias_audit_log(user_id, goal_id, audit_type, audit_result)` — appends a timestamped audit entry, retains last 200 per user
  - `get_bias_audit_log(user_id)` — returns all audit entries for a user
- Each entry structure:
  ```python
  {
      "timestamp": "ISO_TIMESTAMP",
      "goal_id": int,
      "audit_type": "skill_gap_bias" | "profile_fairness" | "content_bias" | "chatbot_bias",
      "overall_risk": "low" | "medium" | "high",
      "flagged_count": int,
      "audited_count": int,
      "flags_summary": [{"category": str, "severity": str}]  # compact summary, not full flags
  }
  ```
- Register in `load()` function alongside other stores

### 2. `backend/main.py`
**a) Auto-persist audit results** — After each of the 4 audit endpoints returns a result, append to the bias audit log:
- `POST /audit-skill-gap-bias` — add `store.append_bias_audit_log(...)` after the audit call
- `POST /validate-profile-fairness` — same
- `POST /audit-content-bias` — same
- `POST /audit-chatbot-bias` — same

**b) New endpoint** — `GET /bias-audit-history/{user_id}` (on `protected_router`):
- Accepts optional `goal_id` query parameter to filter by goal
- Returns the audit log entries from `store.get_bias_audit_log(user_id)`
- Computes summary stats: total audits, risk distribution, most common bias categories

### 3. `frontend/utils/request_api.py`
- Add `"bias_audit_history"` to `API_NAMES` dict mapping to `"bias-audit-history"`
- Add `get_bias_audit_history(user_id, goal_id=None)` function

### 4. `frontend/pages/dashboard.py`
Add a 5th section **"Bias & Ethics Review"** after the existing 4 sections:
- Fetch bias audit history via `get_bias_audit_history(user_id, selected_goal_id)`
- Display:
  - **Summary metrics row** (st.metric): Total audits run, flags detected, current risk level
  - **Risk distribution chart** (st.bar_chart): Count of low/medium/high risk audits
  - **Bias category breakdown** (st.bar_chart): Most common bias categories flagged
  - **Audit timeline** (st.line_chart or table): Recent audit results over time with risk levels
- If no audit history exists, show `st.info("No bias audits recorded yet.")`

### 5. `backend/tests/test_bias_audit_persistence.py` (New)
- Test `append_bias_audit_log` stores and retrieves entries correctly
- Test 200-entry cap per user
- Test `get_bias_audit_log` filtering
- Test the `/bias-audit-history/{user_id}` endpoint returns correct data

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/utils/store.py` | Modify | Add bias audit log persistence |
| `backend/main.py` | Modify | Auto-persist audits + new GET endpoint |
| `frontend/utils/request_api.py` | Modify | Add API helper for bias history |
| `frontend/pages/dashboard.py` | Modify | Add Bias & Ethics Review section |
| `backend/tests/test_bias_audit_persistence.py` | Create | Test persistence and endpoint |

## Verification
1. Run tests: `python -m pytest backend/tests/test_bias_audit_persistence.py -v`
2. Start backend, trigger a bias audit (e.g., via chatbot), then call `GET /bias-audit-history/{user_id}` to verify persistence
3. Start frontend, navigate to Learning Analytics, verify the new Bias & Ethics Review section renders with data
