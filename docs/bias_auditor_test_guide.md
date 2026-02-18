# Bias Auditor — Testing Guide

> **Purpose:** This document provides backend test details and manual frontend verification steps for the **Bias Auditor** module, which audits skill gap assessments for demographic bias, confidence calibration issues, and ethical transparency.
>
> **How to use:** Run the backend tests first to verify correctness, then follow the Streamlit frontend steps to verify the full user experience. Copy into a Google Doc to check off steps and leave comments.
>
> **Prerequisites:** Log in or register. Complete onboarding by selecting a persona, entering a learning goal, and clicking "Begin Learning". Wait for skill gap identification to complete.

---

## Overview

The Bias Auditor is a **post-processing layer** that runs automatically after skill gap identification. It does **not** block the user flow — if the audit endpoint fails, the user proceeds normally with only a hardcoded ethical disclaimer shown.

### What It Checks

| Check | Type | Description |
|-------|------|-------------|
| Bias flag detection | LLM | Scans each skill gap's `reason` for assumption-based rather than evidence-based reasoning |
| Demographic-blind validation | LLM | Checks if assessments are influenced by name, gender, age, institution prestige, or nationality |
| Confidence calibration | Deterministic | Flags low-confidence + extreme-level combinations (e.g., `confidence=low` + `level=unlearned`) |
| Ethical disclaimer | Static | Adds transparency metadata informing learners that assessments are AI-generated |

### Bias Categories

The auditor classifies flags into 7 categories:

| Category | Description |
|----------|-------------|
| `demographic_inference` | Assessment influenced by demographic cues |
| `prestige_bias` | Assessment influenced by institution/employer prestige |
| `gender_assumption` | Assessment influenced by perceived gender |
| `age_assumption` | Assessment influenced by perceived age |
| `nationality_assumption` | Assessment influenced by perceived nationality |
| `stereotype_based` | Assessment uses stereotypical reasoning |
| `unsubstantiated_claim` | Assessment makes claims without supporting evidence |

---

## Backend Test Scripts

| Test file | Class / Tests | What it covers |
|-----------|---------------|----------------|
| `test_bias_auditor.py` | `TestBiasAuditSchemas` (6 tests) | BiasCategory enum values, BiasSeverity enum values, BiasFlag validation (valid flag, explanation word limit, suggestion word limit), BiasAuditResult defaults |
| `test_bias_auditor.py` | `TestConfidenceCalibration` (6 tests) | Deterministic `_check_confidence_calibration`: low confidence + unlearned flagged, low confidence + expert flagged, low confidence + intermediate not flagged, medium/high confidence + extreme not flagged, empty input |
| `test_bias_auditor.py` | `TestBiasAuditorAgent` (5 tests, mocked LLM) | Clean assessment returns no flags, bias flags detected and counted, calibration flags merged with LLM output, risk promoted from "low" to "medium" when calibration flags exist, ethical disclaimer always present |
| `test_bias_auditor.py` | `TestAuditSkillGapBiasWithLlm` (1 test) | Convenience function creates BiasAuditor instance and returns dict |

**Run command:**
```bash
python -m pytest backend/tests/test_bias_auditor.py -v
```

**Expected output:** 18 tests passed.

---

## Streamlit Frontend Test Steps

### Where the Bias Audit Appears

The bias audit results are displayed on the **Skill Gap** page (`pages/skill_gap.py`), after the goal assessment and retrieval source banners, and before the skill gap cards.

**Relevant frontend files:**
- `frontend/components/gap_identification.py` — `render_bias_audit_banners(goal)` and audit call in `render_identifying_skill_gap(goal)`
- `frontend/pages/skill_gap.py` — imports and calls `render_bias_audit_banners(goal)`
- `frontend/utils/request_api.py` — `audit_skill_gap_bias()` API helper

---

### Test 1 — Ethical Disclaimer Always Visible

> **Scenario:** Any learning goal, any persona.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding with any persona and learning goal | Skill gap identification runs. Bias audit runs automatically afterward |
| 2 | Observe the Skill Gap page above the skill cards | An **info banner** (blue) is always visible with the ethical disclaimer: *"These skill assessments are AI-generated inferences based on the information you provided..."* |
| 3 | Even if the bias audit backend call fails | The fallback disclaimer is still shown (hardcoded in the frontend) |

---

### Test 2 — Clean Assessment (No Bias Flags)

> **Scenario:** Use a neutral learning goal with no demographic-heavy background.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select any persona (e.g., "Balanced Learner") | Persona selected |
| 2 | Enter a neutral goal (e.g., "Learn Python for data analysis") | Goal entered |
| 3 | Skip resume upload or upload a neutral resume | No demographic cues provided |
| 4 | Click "Begin Learning", wait for skill gap identification | Skills identified and bias audit runs |
| 5 | Observe the Skill Gap page | Only the **ethical disclaimer** info banner is shown. No warning banner. No "View bias audit details" expander |

---

### Test 3 — Bias Flags Detected (Warning Banner)

> **Scenario:** Provide demographic-heavy background information to trigger bias detection.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select any persona | Persona selected |
| 2 | Enter a learning goal (e.g., "Learn HR Management") | Goal entered |
| 3 | Upload a resume or provide background that includes strong demographic cues (name, gender markers, prestigious university, nationality references, age indicators) | Background with demographic signals |
| 4 | Click "Begin Learning", wait for skill gap identification | Skills identified and bias audit runs |
| 5 | If the LLM detects bias in the skill gap reasoning | A **warning banner** (orange/yellow) appears: *"Moderate/High bias risk detected: X of Y skills flagged. Review the details below and consider adjusting the assessments."* |
| 6 | Click the **"View bias audit details"** expander | Expander opens showing individual bias flags |
| 7 | Verify each bias flag shows | Skill name, bias category (e.g., "prestige_bias"), severity (low/medium/high), explanation, and suggestion |
| 8 | Verify severity icons | Low = yellow circle, Medium = orange circle, High = red circle |

> **Note:** Whether bias flags appear depends on the LLM's analysis. The LLM is calibrated to avoid false positives, so a clean assessment with no flags is also valid behavior. The deterministic confidence calibration check (Test 4) is more reliably reproducible.

---

### Test 4 — Confidence Calibration Warnings

> **Scenario:** The deterministic confidence calibration check flags skills where the LLM assigned low confidence but an extreme level (unlearned or expert).

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete skill gap identification for any goal | Skills identified |
| 2 | Check the "More Analysis Details" expander for each skill | Note any skills where **Confidence Level = low** and **Current Level = unlearned** or **expert** |
| 3 | If such a combination exists | The bias audit details expander should contain a **"Confidence Calibration Warnings"** section with entries like: *"Machine Learning: Low confidence assessment assigned extreme level 'unlearned'. Consider defaulting to a moderate level when confidence is low."* |
| 4 | If calibration flags exist but LLM reported "low" risk | The overall risk is automatically promoted to **"medium"**, and a warning banner appears |

---

### Test 5 — Bias Audit Does Not Block User Flow

> **Scenario:** Verify the audit is non-blocking.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete skill gap identification | Skills shown on the Skill Gap page |
| 2 | Regardless of bias audit result | The "Schedule Learning Path" button is still available (if skill gaps exist) |
| 3 | Click "Schedule Learning Path" | Profile creation proceeds normally. Bias audit result does not affect profile creation or learning path scheduling |
| 4 | If the bias audit endpoint is unavailable (e.g., backend error) | Only the hardcoded ethical disclaimer is shown. No crash. No error message visible to the user (error is silently caught) |

---

### Test 6 — Bias Audit Details in Expander

> **Scenario:** Verify the full structure of the bias audit expander when flags exist.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger bias flags (see Test 3) or calibration flags (see Test 4) | Warning banner and expander are visible |
| 2 | Open the "View bias audit details" expander | Expander opens |
| 3 | Verify **Bias Flags** section (if present) | Each flag shows: severity icon, **skill name** (bold), *bias category* (italic), (severity), explanation text, **Suggestion:** text |
| 4 | Verify **Confidence Calibration Warnings** section (if present) | Each flag shows: warning icon, **skill name** (bold), issue description |

---

### Test 7 — Adjusting Skill Levels After Bias Warning

> **Scenario:** User adjusts skill levels in response to bias warnings.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Observe bias flags for specific skills | Note which skills are flagged |
| 2 | Change the **Current Level** of a flagged skill using the pills selector | Level updates, gap status recalculates (red/green header changes) |
| 3 | Toggle **"Mark as Gap"** off for a flagged skill | Gap removed, current level set to match required |
| 4 | The bias audit result is **not** re-run on level change | The original bias audit banners remain visible. The audit only runs during initial skill gap identification |

---

## Architecture Reference

```
Frontend                           Backend
────────                           ───────
Skill Gap Page
  └─ render_identifying_skill_gap()
       ├─ POST /identify-skill-gap-with-info  (existing)
       │    → returns skill_gaps
       └─ POST /audit-skill-gap-bias  (bias audit)
            → takes skill_gaps + learner_information
            → returns BiasAuditResult
                ├─ bias_flags[]
                ├─ confidence_calibration_flags[]
                ├─ overall_bias_risk (low/medium/high)
                ├─ audited_skill_count
                ├─ flagged_skill_count
                └─ ethical_disclaimer
```

---

## Key Files

| File | Role |
|------|------|
| `backend/modules/skill_gap/schemas.py` | `BiasCategory`, `BiasSeverity`, `BiasFlag`, `ConfidenceCalibrationFlag`, `BiasAuditResult` models |
| `backend/modules/skill_gap/agents/bias_auditor.py` | `BiasAuditor` agent with `audit_skill_gaps()` + deterministic `_check_confidence_calibration()` |
| `backend/modules/skill_gap/prompts/bias_auditor.py` | System prompt and task prompt for the LLM |
| `backend/main.py` | `POST /audit-skill-gap-bias` endpoint |
| `backend/api_schemas.py` | `BiasAuditRequest` request schema |
| `backend/tests/test_bias_auditor.py` | 18 unit tests |
| `frontend/components/gap_identification.py` | `render_bias_audit_banners()` + audit call in `render_identifying_skill_gap()` |
| `frontend/pages/skill_gap.py` | Imports and calls `render_bias_audit_banners()` |
| `frontend/utils/request_api.py` | `audit_skill_gap_bias()` API helper |
