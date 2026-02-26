# Content Bias Auditor — Testing Guide

> **Purpose:** This document provides backend test details and manual frontend verification steps for the **Content Bias Auditor** module, which audits AI-generated learning content for language bias, representation bias, difficulty bias, and source bias.
>
> **How to use:** Run the backend tests first to verify correctness, then follow the Streamlit frontend steps to verify the full user experience. Copy into a Google Doc to check off steps and leave comments.
>
> **Prerequisites:** Log in or register. Complete onboarding (select a persona, enter a learning goal, click "Begin Learning"). Wait for skill gap identification, then schedule a learning path. Navigate to a Knowledge Document session.

---

## Overview

The Content Bias Auditor is a **post-processing layer** that runs automatically after learning content is generated. It does **not** block the user flow — if the audit endpoint fails, the user proceeds normally with only a hardcoded ethical disclaimer shown.

### What It Checks

| Check | Type | Description |
|-------|------|-------------|
| Representation bias detection | LLM | Flags culturally narrow examples, excluded perspectives, or assumed demographic contexts |
| Language bias detection | LLM | Identifies gendered, ableist, or culturally insensitive language |
| Difficulty bias detection | LLM | Checks if content difficulty is influenced by demographics rather than assessed skill level |
| Source bias detection | LLM | Flags content skewed toward a single perspective or cultural context |
| Biased language scanning | Deterministic | Keyword scanning for known biased phrases (e.g., "mankind", "chairman", "suffers from") |
| Ethical disclaimer | Static | Adds transparency metadata informing learners that content is AI-generated |

### Bias Categories

The auditor classifies flags into 4 categories:

| Category | Description |
|----------|-------------|
| `representation_bias` | Content uses culturally narrow examples, excludes diverse perspectives, or assumes a specific demographic context |
| `language_bias` | Content contains gendered, ableist, or culturally insensitive language |
| `difficulty_bias` | Content difficulty appears influenced by learner demographics rather than assessed proficiency |
| `source_bias` | Content or sources are skewed toward a single perspective or cultural context |

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

---

## Backend Test Scripts

| Test file | Class / Tests | What it covers |
|-----------|---------------|----------------|
| `test_content_bias_auditor.py` | `TestContentBiasAuditSchemas` (6 tests) | ContentBiasCategory enum values, ContentBiasSeverity enum values, ContentBiasFlag validation (valid flag, explanation word limit, suggestion word limit), ContentBiasAuditResult defaults |
| `test_content_bias_auditor.py` | `TestBiasedLanguageCheck` (9 tests) | Deterministic `_check_biased_language`: detects "mankind", "chairman", "suffers from", "confined to a wheelchair", clean content not flagged, empty input, multiple terms detected, correct category assigned, alternatives suggested |
| `test_content_bias_auditor.py` | `TestSectionCount` (3 tests) | `_count_sections`: counts markdown headers, no headers returns 1, empty content returns 1 |
| `test_content_bias_auditor.py` | `TestContentBiasAuditorAgent` (5 tests, mocked LLM) | Clean content returns no flags, LLM bias flags detected and counted, deterministic flags merged with LLM output, risk promoted from "low" to "medium" when deterministic flags exist, ethical disclaimer always present |
| `test_content_bias_auditor.py` | `TestAuditContentBiasWithLlm` (1 test) | Convenience function creates ContentBiasAuditor instance and returns dict |

**Run command:**
```bash
python -m pytest backend/tests/test_content_bias_auditor.py -v
```

**Expected output:** 24 tests passed.

---

## Streamlit Frontend Test Steps

### Where the Content Bias Audit Appears

The content bias audit results are displayed on the **Knowledge Document** page (`pages/knowledge_document.py`), after the content format badge (podcast/visual) and before the document content sections.

**Relevant frontend files:**
- `frontend/components/content_bias.py` — `render_content_bias_banners(goal)` component
- `frontend/pages/knowledge_document.py` — imports and calls `render_content_bias_banners(goal)`, calls `audit_content_bias()` after content generation
- `frontend/utils/request_api.py` — `audit_content_bias()` API helper

---

### Test 1 — Ethical Disclaimer Always Visible

> **Scenario:** Any learning goal, any persona.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding, schedule a learning path, navigate to a Knowledge Document session | Content is generated. Content bias audit runs automatically afterward |
| 2 | Observe the Knowledge Document page above the document content | An **info banner** (blue) is always visible with the ethical disclaimer: *"This learning content was generated by an AI system..."* |
| 3 | Even if the content bias audit backend call fails | The fallback disclaimer is still shown (hardcoded in the frontend) |

---

### Test 2 — Clean Content (No Bias Flags)

> **Scenario:** Use a neutral, technical learning goal.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select any persona (e.g., "Balanced Learner") | Persona selected |
| 2 | Enter a technical goal (e.g., "Learn Python data structures") | Goal entered |
| 3 | Complete onboarding, schedule learning path, open a Knowledge Document session | Content generated and bias audit runs |
| 4 | Observe the Knowledge Document page | Only the **ethical disclaimer** info banner is shown. No warning banner. No "View content bias audit details" expander |

---

### Test 3 — Bias Flags Detected (Warning Banner)

> **Scenario:** Generated content contains biased elements flagged by the LLM.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete content generation for any session | Content displayed |
| 2 | If the LLM detects bias in the generated content | A **warning banner** (orange/yellow) appears: *"Moderate/High content bias risk detected: X of Y sections flagged. Review the details below."* |
| 3 | Click the **"View content bias audit details"** expander | Expander opens showing individual bias flags |
| 4 | Verify each bias flag shows | Section title, bias category (e.g., "representation_bias"), severity (low/medium/high), explanation, and suggestion |
| 5 | Verify severity icons | Low = yellow circle, Medium = orange circle, High = red circle |

> **Note:** Whether LLM-based bias flags appear depends on the content generated. The deterministic language check (Test 4) is more reliably reproducible.

---

### Test 4 — Deterministic Language Bias Detection

> **Scenario:** Generated content happens to contain known biased phrases.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete content generation for any session | Content generated |
| 2 | If the generated content contains any of the 15 tracked biased phrases (e.g., "mankind", "chairman") | The bias audit details expander should contain a **"Language Bias Warnings"** section with entries like: *"The phrase 'mankind' was detected in the content. This may be considered non-inclusive language."* with a suggestion to use the inclusive alternative |
| 3 | If deterministic flags exist but LLM reported "low" risk | The overall risk is automatically promoted to **"medium"**, and a warning banner appears |

---

### Test 5 — Content Bias Audit Does Not Block User Flow

> **Scenario:** Verify the audit is non-blocking.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Navigate to a Knowledge Document session | Content generated and displayed |
| 2 | Regardless of content bias audit result | The document content, quizzes, and all other page features work normally |
| 3 | If the content bias audit endpoint is unavailable (e.g., backend error) | Only the hardcoded ethical disclaimer is shown. No crash. No error message visible to the user (error is silently caught) |

---

### Test 6 — Content Bias Details in Expander

> **Scenario:** Verify the full structure of the bias audit expander when flags exist.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger bias flags (see Test 3) or language flags (see Test 4) | Warning banner and expander are visible |
| 2 | Open the "View content bias audit details" expander | Expander opens |
| 3 | Verify **Content Bias Flags** section (if present) | Each flag shows: severity icon, **section title** (bold), *bias category* (italic), (severity), explanation text, **Suggestion:** text |
| 4 | Verify **Language Bias Warnings** section (if present) | Each flag shows: warning icon, explanation of the biased phrase detected, **Suggestion:** inclusive alternative |

---

## Architecture Reference

```
Frontend                           Backend
────────                           ───────
Knowledge Document Page
  └─ render_content_preparation()
       ├─ POST /integrate-learning-document  (existing)
       │    → returns learning_content
       └─ POST /audit-content-bias  (content bias audit)
            → takes generated_content + learner_information
            → returns ContentBiasAuditResult
                ├─ bias_flags[]
                ├─ deterministic_flags[]
                ├─ overall_bias_risk (low/medium/high)
                ├─ audited_section_count
                ├─ flagged_section_count
                └─ ethical_disclaimer
```

---

## Key Files

| File | Role |
|------|------|
| `backend/modules/content_generator/schemas.py` | `ContentBiasCategory`, `ContentBiasSeverity`, `ContentBiasFlag`, `ContentBiasAuditResult` models |
| `backend/modules/content_generator/agents/content_bias_auditor.py` | `ContentBiasAuditor` agent with `audit_content()` + deterministic `_check_biased_language()` |
| `backend/modules/content_generator/prompts/content_bias_auditor.py` | System prompt and task prompt for the LLM |
| `backend/main.py` | `POST /audit-content-bias` endpoint |
| `backend/api_schemas.py` | `ContentBiasAuditRequest` request schema |
| `backend/tests/test_content_bias_auditor.py` | 24 unit tests |
| `frontend/components/content_bias.py` | `render_content_bias_banners()` banner component |
| `frontend/pages/knowledge_document.py` | Imports and calls `render_content_bias_banners()`, triggers audit after content generation |
| `frontend/utils/request_api.py` | `audit_content_bias()` API helper |
| `backend/implementation_plan/20260225/content-bias-auditor-implementation-plan.md` | Full implementation plan |
