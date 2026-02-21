# Fairness Validator — Testing Guide

> **Purpose:** This document provides backend test details and manual frontend verification steps for the **Fairness Validator** module, which validates learner profiles for fairness in FSLSM dimensions, stereotype language, and ethical transparency.
>
> **How to use:** Run the backend tests first to verify correctness, then follow the Streamlit frontend steps to verify the full user experience. Copy into a Google Doc to check off steps and leave comments.
>
> **Prerequisites:** Log in or register. Complete onboarding by selecting a persona, entering a learning goal, and clicking "Begin Learning". Wait for skill gap identification to complete, then click "Schedule Learning Path" to create a learner profile.

---

## Overview

The Fairness Validator is a **post-processing layer** that runs automatically after learner profile creation (when the user clicks "Schedule Learning Path"). It does **not** block the user flow — if the validation endpoint fails, the user proceeds normally with only a hardcoded ethical disclaimer shown.

### What It Checks

| Check | Type | Description |
|-------|------|-------------|
| Fairness flag detection | LLM | Scans the profile for unjustified FSLSM deviations, missing SOLO justifications, confidence without evidence |
| FSLSM deviation from persona baseline | Deterministic | Compares profile FSLSM dimensions against the selected persona's baseline; flags deviations > 0.4 |
| Stereotype keyword scan | Deterministic | Scans profile text fields for 10 known stereotype phrases (e.g., "as an engineer", "naturally inclined") |
| Ethical disclaimer | Static | Adds transparency metadata informing learners that the profile is AI-generated |

### Fairness Categories

The validator classifies flags into 4 categories:

| Category | Description |
|----------|-------------|
| `fslsm_unjustified_deviation` | FSLSM dimension shifted from persona baseline without supporting evidence |
| `solo_missing_justification` | Proficiency level assigned without clear SOLO taxonomy justification |
| `confidence_without_evidence` | Assessment field set confidently despite insufficient evidence |
| `stereotypical_language` | Profile text contains assumption-based or stereotypical language |

### Persona Baselines (FSLSM)

The validator compares profile FSLSM dimensions against these persona baselines:

| Persona | Processing | Perception | Input | Understanding |
|---------|-----------|------------|-------|---------------|
| Hands-on Explorer | -0.7 | -0.5 | -0.5 | -0.5 |
| Reflective Reader | 0.7 | 0.5 | 0.7 | 0.5 |
| Visual Learner | -0.2 | -0.3 | -0.8 | -0.3 |
| Conceptual Thinker | 0.5 | 0.7 | 0.0 | 0.7 |
| Balanced Learner | 0.0 | 0.0 | 0.0 | 0.0 |

Deviations **greater than 0.4** from the baseline are flagged.

### Stereotype Phrases Detected

The following phrases trigger deterministic flags when found in profile text fields:

`"as an engineer"`, `"typical for"`, `"as expected from"`, `"naturally inclined"`, `"inherently"`, `"as a woman"`, `"as a man"`, `"given their age"`, `"from that background"`, `"people from"`

---

## Backend Test Scripts

| Test file | Class / Tests | What it covers |
|-----------|---------------|----------------|
| `test_fairness_validator.py` | `TestFairnessSchemas` (6 tests) | FairnessCategory enum values, FairnessSeverity enum values, FairnessFlag validation (valid flag, explanation word limit, suggestion word limit), ProfileFairnessResult defaults |
| `test_fairness_validator.py` | `TestFSLSMDeviationCheck` (7 tests) | Deterministic `_check_fslsm_deviation`: large deviation flagged (1.2 for processing), all dimensions checked, matching persona not flagged, small deviation (0.3) not flagged, no persona skips check, unknown persona skips check, Balanced Learner (all 0.0) not flagged |
| `test_fairness_validator.py` | `TestStereotypeKeywordCheck` (5 tests) | Deterministic `_check_stereotype_keywords`: stereotype in additional_notes, stereotype in motivational_triggers, clean profile no flags, empty fields no flags, multiple phrases produce multiple flags |
| `test_fairness_validator.py` | `TestFairnessValidatorAgent` (6 tests, mocked LLM) | Clean profile returns no flags, fairness flags detected and counted, FSLSM deviation flags merged with LLM output, stereotype flags merged, risk promoted from "low" to "medium" when deterministic flags exist, ethical disclaimer always present |
| `test_fairness_validator.py` | `TestValidateProfileFairnessWithLlm` (1 test) | Convenience function creates FairnessValidator instance and returns dict |

**Run command:**
```bash
python -m pytest backend/tests/test_fairness_validator.py -v
```

**Expected output:** 25 tests passed.

---

## Streamlit Frontend Test Steps

### Where the Fairness Validation Appears

The fairness validation results are displayed on the **My Profile** page (`pages/learner_profile.py`), between the Learner Information/Learning Goal section and the Cognitive Status section.

The validation runs when the user clicks "Schedule Learning Path" on the Skill Gap page. Results are stored in `goal["profile_fairness"]` and displayed on subsequent visits to My Profile.

**Relevant frontend files:**
- `frontend/pages/learner_profile.py` — `render_fairness_banners(goal)` called from `render_learner_profile_info()`
- `frontend/pages/skill_gap.py` — calls `validate_profile_fairness()` after `create_learner_profile()`
- `frontend/utils/request_api.py` — `validate_profile_fairness()` API helper

---

### Test 1 — Ethical Disclaimer Always Visible

> **Scenario:** Any learning goal, any persona.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete onboarding, identify skill gaps, click "Schedule Learning Path" | Profile is created and fairness validation runs automatically |
| 2 | Navigate to **My Profile** | An **info banner** (blue) is visible below the Learner Information/Learning Goal section: *"This learner profile was generated by AI based on limited information..."* |
| 3 | Even if the fairness validation backend call fails | The fallback disclaimer is still shown (hardcoded in the frontend) |

---

### Test 2 — Clean Profile (No Fairness Flags)

> **Scenario:** Use a persona with background that matches the persona baseline.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select "Hands-on Explorer" persona | Persona selected |
| 2 | Enter a neutral goal (e.g., "Learn Python for data analysis") | Goal entered |
| 3 | Skip resume upload or upload a neutral resume (no stereotype phrases) | No demographic cues |
| 4 | Click "Begin Learning", wait for skill gaps, click "Schedule Learning Path" | Profile created, fairness validation runs |
| 5 | Navigate to **My Profile** | Only the **ethical disclaimer** info banner is shown. No warning banner. No "View profile fairness details" expander |

---

### Test 3 — FSLSM Deviation Flags

> **Scenario:** Trigger FSLSM deviation detection by having the LLM generate a profile that deviates from the persona baseline.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Select **"Hands-on Explorer"** (processing = -0.7, active learner) | Persona selected |
| 2 | Upload a resume or provide background that emphasizes reflective, theoretical learning style | Background contradicts the persona |
| 3 | Complete skill gap identification and click "Schedule Learning Path" | Profile created. If the LLM shifted FSLSM dimensions away from persona baseline (e.g., processing from -0.7 to +0.5), deviation flags are generated |
| 4 | Navigate to **My Profile** | A **warning banner** (orange/yellow) appears: *"Moderate fairness risk detected: X of Y fields flagged."* |
| 5 | Click the **"View profile fairness details"** expander | Expander opens |
| 6 | Verify **FSLSM Deviation Warnings** section | Shows dimension name, persona baseline value, profile value, and deviation amount (e.g., *"fslsm_processing: Persona baseline -0.7 -> Profile value 0.5 (deviation: 1.2)"*) |

> **Note:** FSLSM deviations depend on the LLM's profile generation. If the LLM respects the persona baseline, no deviation flags will appear — this is correct behavior. The deterministic check only flags deviations > 0.4.

---

### Test 4 — Stereotype Language Detection

> **Scenario:** Trigger stereotype keyword detection. This is deterministic and reliably reproducible.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | If the LLM generates a profile containing phrases like "as an engineer", "naturally inclined", "typical for", etc. in the `additional_notes` or `motivational_triggers` fields | Stereotype flags are generated |
| 2 | Navigate to **My Profile** | Warning banner appears if flags were detected |
| 3 | Open the **"View profile fairness details"** expander | **Fairness Flags** section shows flags with category `stereotypical_language`, explanation citing the specific phrase, and suggestion to use evidence-based descriptions |

> **Note:** The 10 detected phrases are: "as an engineer", "typical for", "as expected from", "naturally inclined", "inherently", "as a woman", "as a man", "given their age", "from that background", "people from". These are scanned in `learner_information`, `learning_preferences.additional_notes`, `behavioral_patterns.additional_notes`, and `behavioral_patterns.motivational_triggers`.

---

### Test 5 — Fairness Flags from LLM

> **Scenario:** The LLM may detect additional fairness issues beyond the deterministic checks.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Complete profile creation with a rich background | Fairness validation runs |
| 2 | If the LLM flags issues (e.g., `solo_missing_justification`, `confidence_without_evidence`) | These flags appear alongside any deterministic flags in the expander |
| 3 | Verify each fairness flag shows | Field name, fairness category, severity (low/medium/high), severity icon, explanation, and suggestion |

---

### Test 6 — Fairness Validation Does Not Block User Flow

> **Scenario:** Verify the validation is non-blocking.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Click "Schedule Learning Path" on the Skill Gap page | Spinner: "Creating your profile ...". Profile is created |
| 2 | Regardless of fairness validation result | User is navigated to the **Learning Path** page. Profile creation and learning path scheduling proceed normally |
| 3 | Navigate to **My Profile** | Fairness banners are shown (if available) but do not prevent access to any profile features |
| 4 | If the fairness validation endpoint is unavailable | Only the hardcoded ethical disclaimer is shown on My Profile. No crash. No error message visible (error is silently caught) |

---

### Test 7 — Risk Promotion Logic

> **Scenario:** Verify that deterministic flags promote the overall risk level.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | If the LLM reports `overall_fairness_risk = "low"` but deterministic checks find FSLSM deviations or stereotype phrases | The overall risk is automatically promoted to **"medium"** |
| 2 | The warning banner reflects the promoted risk | *"Moderate fairness risk detected..."* |

---

### Test 8 — Fairness Details Expander Structure

> **Scenario:** Verify the full structure of the fairness expander when flags exist.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Trigger fairness flags (see Tests 3-5) | Warning banner and expander are visible on My Profile |
| 2 | Open the **"View profile fairness details"** expander | Expander opens |
| 3 | Verify **Fairness Flags** section (if present) | Each flag shows: severity icon (yellow/orange/red circle), **field name** (bold), *fairness category* (italic), (severity), explanation text, **Suggestion:** text |
| 4 | Verify **FSLSM Deviation Warnings** section (if present) | Each flag shows: warning icon, **dimension name** (bold), persona baseline value, arrow, profile value, (deviation amount) |

---

## Architecture Reference

```
Frontend                           Backend
────────                           ───────
Skill Gap Page
  └─ "Schedule Learning Path" button
       ├─ POST /create-learner-profile-with-info  (existing)
       │    → returns learner_profile
       └─ POST /validate-profile-fairness  (fairness validation)
            → takes learner_profile + learner_information + persona_name
            → returns ProfileFairnessResult
                ├─ fairness_flags[]
                ├─ fslsm_deviation_flags[]
                ├─ overall_fairness_risk (low/medium/high)
                ├─ checked_fields_count
                ├─ flagged_fields_count
                └─ ethical_disclaimer

My Profile Page
  └─ render_fairness_banners(goal)
       → reads goal["profile_fairness"]
       → shows disclaimer, warning, expander
```

---

## Key Files

| File | Role |
|------|------|
| `backend/modules/learner_profiler/schemas.py` | `FairnessCategory`, `FairnessSeverity`, `FairnessFlag`, `FSLSMDeviationFlag`, `ProfileFairnessResult` models |
| `backend/modules/learner_profiler/agents/fairness_validator.py` | `FairnessValidator` agent with `validate_profile()` + deterministic `_check_fslsm_deviation()` and `_check_stereotype_keywords()` |
| `backend/modules/learner_profiler/prompts/fairness_validator.py` | System prompt and task prompt for the LLM |
| `backend/main.py` | `POST /validate-profile-fairness` endpoint |
| `backend/api_schemas.py` | `ProfileFairnessRequest` request schema |
| `backend/tests/test_fairness_validator.py` | 25 unit tests |
| `frontend/pages/learner_profile.py` | `render_fairness_banners()` display logic |
| `frontend/pages/skill_gap.py` | Calls `validate_profile_fairness()` after profile creation |
| `frontend/utils/request_api.py` | `validate_profile_fairness()` API helper |
