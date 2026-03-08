# Content Bias Auditor Module — Implementation Plan

**Branch:** `sprint-4-ethics-bias-enhancement`
**Date:** 2026-02-25
**Project:** Ami (5902Group5)

---

## 1. Context

The AI Tutor system generates personalized learning content adapted to each learner's cognitive style (FSLSM dimensions) and proficiency level (SOLO taxonomy). Currently, there are **zero checks** for whether this generated content contains biased language, culturally narrow examples, demographic-influenced difficulty, or skewed source perspectives. This module adds a post-processing content bias audit layer that reviews generated learning content for fairness — completely non-overlapping with existing functionality.

The existing **Bias Auditor** (skill gap) and **Fairness Validator** (learner profile) cover two modules. This Content Bias Auditor extends ethics coverage to a third — and arguably the most learner-facing — module: the Content Generator.

---

## 2. Objectives

1. **Representation bias detection** (LLM) — Flags content that uses culturally narrow examples, excludes diverse perspectives, or presents scenarios that assume a specific demographic background
2. **Language bias detection** (LLM) — Identifies gendered language, ableist terms, or culturally insensitive framing in generated content
3. **Difficulty bias detection** (LLM) — Checks if content difficulty appears influenced by learner demographics rather than assessed skill level
4. **Source bias detection** (LLM) — Flags when retrieved or generated resources appear skewed toward a single perspective or cultural context
5. **Deterministic biased language check** — Keyword scanning for known biased/stereotypical phrases
6. **Ethical disclaimer** — Adds transparency metadata informing learners that content is AI-generated
7. **Frontend display** — Makes all of the above visible to the user on the Knowledge Document page

---

## 3. Architecture

Strictly a **post-processing layer** — takes existing generated content as input, returns an audit report. Zero modifications to the existing content generation pipeline.

```
POST /integrate-learning-document  (existing, unchanged)
  -> returns learning_content (document, quizzes, sources)

POST /audit-content-bias  (NEW)
  -> takes generated_content + learner_information
  -> returns content bias audit report
```

---

## 4. Files to Create / Modify

### 4.1 New Files (3)

| File | Purpose |
|------|---------|
| `backend/modules/content_generator/prompts/content_bias_auditor.py` | System prompt + task prompt |
| `backend/modules/content_generator/agents/content_bias_auditor.py` | `ContentBiasAuditor` agent class + `audit_content_bias_with_llm()` convenience function |
| `backend/tests/test_content_bias_auditor.py` | Tests for schemas, deterministic checks, and mocked LLM audit |

### 4.2 Modified Files — Backend (4)

| File | Change |
|------|--------|
| `backend/modules/content_generator/schemas.py` | Add `ContentBiasCategory`, `ContentBiasSeverity` enums + `ContentBiasFlag`, `ContentBiasAuditResult` models |
| `backend/modules/content_generator/agents/__init__.py` | Export `ContentBiasAuditor`, `audit_content_bias_with_llm` |
| `backend/api_schemas.py` | Add `ContentBiasAuditRequest` class |
| `backend/main.py` | Add `POST /audit-content-bias` endpoint |

### 4.3 Modified Files — Frontend (3)

| File | Change |
|------|--------|
| `frontend/utils/request_api.py` | Add `"audit_content_bias"` to `API_NAMES` dict + new `audit_content_bias()` helper function |
| `frontend/pages/knowledge_document.py` | Call audit endpoint after content is generated, store result, and render content bias banners |
| `frontend/components/gap_identification.py` | Add `render_content_bias_banners(goal)` function (or create a new `content_bias.py` component if cleaner) |

---

## 5. Implementation Steps

### Step 1: Schemas (`backend/modules/content_generator/schemas.py`)

Add at the end of the file:

- **`ContentBiasCategory`** enum (str, Enum): `representation_bias`, `language_bias`, `difficulty_bias`, `source_bias`
- **`ContentBiasSeverity`** enum (str, Enum): `low`, `medium`, `high`
- **`ContentBiasFlag`** model:
  - `section_title: str` — Title of the content section being flagged
  - `bias_category: ContentBiasCategory` — Category of the potential bias detected
  - `severity: ContentBiasSeverity` — Severity of the potential bias
  - `explanation: str` — Brief explanation of why this was flagged (max 40 words, validated)
  - `suggestion: str` — Suggested remediation (max 30 words, validated)
- **`ContentBiasAuditResult`** model:
  - `bias_flags: List[ContentBiasFlag]` — LLM-detected bias flags
  - `deterministic_flags: List[ContentBiasFlag]` — Deterministic keyword-based flags
  - `overall_bias_risk: ContentBiasSeverity` — Overall bias risk (low/medium/high)
  - `audited_section_count: int` — Number of content sections audited
  - `flagged_section_count: int` — Number of content sections with at least one flag
  - `ethical_disclaimer: str` — Default text: "This learning content was generated by an AI system. It may reflect biases present in its training data or source materials. If you notice content that seems biased, culturally insensitive, or inappropriate, please report it so we can improve."

### Step 2: Prompts (`backend/modules/content_generator/prompts/content_bias_auditor.py`)

- **System prompt**: Defines the Content Bias Auditor role with directives to:
  - Scan generated content for representation gaps (culturally narrow examples, excluded perspectives)
  - Detect language bias (gendered, ableist, culturally insensitive terms)
  - Check if content difficulty is grounded in assessed skill level, not demographic assumptions
  - Evaluate source diversity and perspective balance
  - Use the 4 bias categories for classification
  - Be calibrated, not alarmist (empty flags list is valid)
  - Assign `overall_bias_risk` (low/medium/high) based on flag count and severity
  - NOT rewrite the content — only audit and flag issues
  - Output valid JSON matching the defined format
- **Task prompt**: Takes `{generated_content}` and `{learner_information}` as placeholders
- Update `prompts/__init__.py` to export the new prompts

### Step 3: Agent (`backend/modules/content_generator/agents/content_bias_auditor.py`)

- **`ContentBiasAuditPayload`**: Pydantic input model with `generated_content` (str) and `learner_information` (str)
- **`ContentBiasAuditor(BaseAgent)`**:
  - Constructor: `super().__init__(model, system_prompt, jsonalize_output=True)` — no tools needed
  - `audit_content()` method:
    1. Validate input with `ContentBiasAuditPayload`
    2. Call `self.invoke()` — LLM returns `bias_flags` + `overall_bias_risk`
    3. Run deterministic `_check_biased_language()` — keyword scanning for known biased phrases
    4. Merge LLM output with deterministic flags
    5. Compute `audited_section_count` and `flagged_section_count`
    6. Promote `overall_bias_risk` to "medium" if deterministic flags exist but LLM said "low"
    7. Validate with `ContentBiasAuditResult` Pydantic model, return `model_dump()`
  - `_check_biased_language()` static method: scans content text for known biased phrases (e.g., "mankind", "chairman", "he/she" defaults, "normal people", "suffers from", "confined to a wheelchair", "third world", "primitive")
- **`audit_content_bias_with_llm()`**: Top-level convenience function
- Update `agents/__init__.py` to export

### Step 4: API Layer

- **`api_schemas.py`**: Add `ContentBiasAuditRequest(BaseRequest)` with `generated_content: str` and `learner_information: str`
- **`main.py`**: Add `POST /audit-content-bias` endpoint:
  - Call `audit_content_bias_with_llm(llm, generated_content, learner_information)`
  - Return result, wrap in try/except with 500 fallback

### Step 5: Tests (`backend/tests/test_content_bias_auditor.py`)

Include `sys.path.insert` at the top (matching pattern from other test files).

**Test classes:**

- **`TestContentBiasAuditSchemas`** — Validate ContentBiasFlag word limits, enum values, ContentBiasAuditResult defaults
- **`TestBiasedLanguageCheck`** — Test the deterministic `_check_biased_language` method:
  - Content with "mankind" -> flagged
  - Content with "chairman" -> flagged
  - Content with "suffers from" -> flagged
  - Clean content -> not flagged
  - Empty input -> empty output
  - Multiple biased terms -> multiple flags
- **`TestContentBiasAuditorAgent`** (mocked LLM) — Clean content, bias flags detected, deterministic flags merged, risk promotion, ethical disclaimer present
- **`TestAuditContentBiasWithLlm`** — Convenience function creates auditor and returns dict

### Step 6: Frontend Integration

#### 6a: API helper (`frontend/utils/request_api.py`)

- Add `"audit_content_bias": "audit-content-bias"` to `API_NAMES` dict
- Add new `audit_content_bias(generated_content, learner_information, llm_type)` function that calls the endpoint via `make_post_request`

#### 6b: Content bias banners (`frontend/components/gap_identification.py` or new `frontend/components/content_bias.py`)

- Add new function `render_content_bias_banners(goal)` that:
  1. Retrieves stored audit result from `goal.get("content_bias_audit")`
  2. **Always** shows the ethical disclaimer as `st.info()`
  3. If `overall_bias_risk` is "medium" or "high", shows `st.warning()` with summary
  4. Shows individual bias flags in an expander ("View content bias audit details") with: section title, category, severity, explanation, suggestion
  5. Shows deterministic flags if any

#### 6c: Knowledge document page (`frontend/pages/knowledge_document.py`)

- Import `render_content_bias_banners`
- Call `audit_content_bias()` after content is generated/loaded and store result in `goal["content_bias_audit"]`
- Call `render_content_bias_banners(goal)` before the document content is rendered (after the content format badge area)

---

## 6. Frontend Display Behavior

| Scenario | What the user sees |
|----------|-------------------|
| No bias flags, low risk | Ethical disclaimer (info banner) only |
| Bias flags detected (medium/high risk) | Ethical disclaimer + warning banner + expandable details per flag |
| Biased language detected (deterministic) | Additional warnings for specific phrases with suggested alternatives |
| Audit endpoint fails | Ethical disclaimer shown anyway (hardcoded fallback), no crash |

---

## 7. Verification

```bash
# Run new tests
python -m pytest backend/tests/test_content_bias_auditor.py -v

# Verify existing tests still pass (no regressions)
python -m pytest backend/tests/ -v

# Manual end-to-end test
# 1. Start backend and frontend
# 2. Go through onboarding with a learning goal
# 3. Schedule a learning path and navigate to a Knowledge Document session
# 4. On the Knowledge Document page, verify:
#    - Ethical disclaimer banner is visible
#    - If bias flags exist, warning banner + expandable details appear
#    - Existing document content still renders correctly
#    - Quizzes and audio/visual content are unaffected
```

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Post-processing layer, not inline | Zero risk of breaking existing content pipeline; can be toggled independently |
| Placed inside `modules/content_generator/` | Consistent with existing pattern (bias auditor in `skill_gap/`, fairness validator in `learner_profiler/`) |
| LLM-based + deterministic checks combined | LLM handles nuanced contextual bias; deterministic checks catch known biased terms reliably |
| 4 bias categories (not 7) | Content bias has fewer distinct categories than skill gap bias; keeping it focused avoids over-flagging |
| "Be calibrated, not alarmist" prompt directive | Prevents over-flagging which would erode user trust |
| Ethical disclaimer always shown | Transparency is valuable regardless of whether bias is detected |
| Targets Knowledge Document page | This is where learners interact with generated content most directly |
| Non-blocking design | Audit failure must never prevent content delivery |
