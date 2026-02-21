# Implementation Plan: FSLSM Tight Integration — Remaining Vectors into Content Generator

**Date**: 2026-02-18
**Sprint**: 3 — Agentic Content Generator
**Branch**: `sprint-3-agentic-content-generator`

---

## Overview

Extends the content generator pipeline to adapt to the three FSLSM dimensions that were previously unhandled:

| Dimension | Key | Range | Pipeline Stage |
|-----------|-----|-------|---------------|
| Processing | `fslsm_processing` | -1 (Active) to +1 (Reflective) | Drafter (per-section) |
| Perception | `fslsm_perception` | -1 (Sensing) to +1 (Intuitive) | Drafter (per-section) |
| Understanding | `fslsm_understanding` | -1 (Sequential) to +1 (Global) | Integrator (document-level) |

All three dimensions use the same thresholds already established for `fslsm_input`:

| Score range | Interpretation |
|-------------|----------------|
| ≤ -0.7 | Strong preference for negative pole |
| -0.7 to -0.3 | Moderate preference for negative pole |
| -0.3 to +0.3 | Balanced / no strong preference |
| +0.3 to +0.7 | Moderate preference for positive pole |
| ≥ +0.7 | Strong preference for positive pole |

Hint strings are built deterministically from FSLSM scores (no LLM involved) and injected as additional instructions into existing task prompts — identical to the `{visual_formatting_hints}` pattern already in place.

---

## Hint Content

### Processing + Perception (`_processing_perception_hints`) → injected into Drafter

| Dimension | Score | Injected instruction |
|-----------|-------|----------------------|
| Processing Active | ≤ -0.3 | After each concept: include `🔧 Try It First` — hands-on challenge/simulation before the full explanation |
| Processing Reflective | ≥ +0.3 | After each concept: include `🤔 Reflection Pause` — one deep-thinking question connecting the concept to prior knowledge |
| Perception Sensing | ≤ -0.3 | Order: (1) concrete real-world example, (2) step-by-step facts/procedure, (3) theory last |
| Perception Intuitive | ≥ +0.3 | Order: (1) abstract principle/theory, (2) relationships & patterns, (3) concrete examples last |

### Understanding (`_understanding_hints`) → injected into Integrator

| Score | Injected instruction |
|-------|----------------------|
| ≤ -0.3 | Strict linear order; explicit "Building on [X]..." transitions; no forward references |
| ≥ +0.3 | Start with `🗺️ Big Picture` section showing how session fits in course; cross-references between sections |

---

## Modified Pipeline (`create_learning_content_with_llm`, genmentor branch)

```
1. explore_knowledge_points_with_llm()
2. _get_fslsm_input() + _visual_formatting_hints()        ← unchanged
2b. _get_fslsm_dim("fslsm_processing") + _get_fslsm_dim("fslsm_perception")
    → _processing_perception_hints(processing, perception) = proc_perc_hints
    _get_fslsm_dim("fslsm_understanding")
    → _understanding_hints(understanding)                  = und_hints
3. draft_knowledge_points_with_llm(
       ...,
       visual_formatting_hints=hints,
       processing_perception_hints=proc_perc_hints        ← NEW
   )
4. [fslsm_input ≤ -0.3] find_media_resources()            ← unchanged
5. integrate_learning_document_with_llm(
       ...,
       media_resources=media_resources,
       understanding_hints=und_hints                      ← NEW
   )
6–9. podcast / TTS / quiz                                  ← unchanged
```

---

## Files Modified (5 files)

### `backend/modules/content_generator/agents/learning_content_creator.py`

Added three new module-level helpers:

**`_get_fslsm_dim(learner_profile, dim_name: str) -> float`**
- Generic parameterised extractor. Same safe extraction logic as `_get_fslsm_input` (handles `str`, `dict`, missing keys, `TypeError`/`ValueError`) but reads any key from `learning_preferences.fslsm_dimensions`.

**`_processing_perception_hints(processing: float, perception: float) -> str`**
- Returns a combined per-section instruction block for the Processing and Perception dimensions.
- Empty string when both scores are in (-0.3, +0.3).

**`_understanding_hints(understanding: float) -> str`**
- Returns a document-level structure instruction for the Understanding dimension.
- Empty string when score is in (-0.3, +0.3).

Modified `create_learning_content_with_llm()` genmentor branch:
- Added **step 2b** after existing step 2: extract all three dimensions and compute both hint strings.
- Passed `processing_perception_hints=proc_perc_hints` into `draft_knowledge_points_with_llm()` (step 3).
- Passed `understanding_hints=und_hints` into `integrate_learning_document_with_llm()` (step 5).

---

### `backend/modules/content_generator/agents/search_enhanced_knowledge_drafter.py`

- Added `processing_perception_hints: str = ""` field to `KnowledgeDraftPayload`.
- Added `processing_perception_hints: str = ""` parameter to `draft_knowledge_point_with_llm()` — threaded into payload dict.
- Added `processing_perception_hints: str = ""` parameter to `draft_knowledge_points_with_llm()` — threaded into `draft_one()` closure.

---

### `backend/modules/content_generator/prompts/search_enhanced_knowledge_drafter.py`

Appended `{processing_perception_hints}` after `{visual_formatting_hints}` in `search_enhanced_knowledge_drafter_task_prompt`. When the hint string is empty the prompt is identical to before.

---

### `backend/modules/content_generator/agents/learning_document_integrator.py`

- Added `understanding_hints: str = ""` field to `IntegratedDocPayload`.
- Added `understanding_hints: str = ""` parameter to `integrate_learning_document_with_llm()` — included in `input_dict` passed to the agent.

---

### `backend/modules/content_generator/prompts/learning_document_integrator.py`

Appended `{understanding_hints}` after `{knowledge_drafts}` in `integrated_document_generator_task_prompt`. When the hint string is empty the prompt is identical to before.

---

## Files Modified — Tests

### `backend/tests/test_adaptive_content_delivery.py`

Added three new test classes (no LLM or network calls):

**`TestGetFslsmDim`** (5 tests)
- Extracts `fslsm_processing`, `fslsm_perception`, `fslsm_understanding` correctly.
- Missing dimension key returns `0.0`.
- Empty profile returns `0.0`.

**`TestProcessingPerceptionHints`** (7 tests)
- Active processing (≤ -0.3) → hint contains `"Try It First"`.
- Reflective processing (≥ +0.3) → hint contains `"Reflection Pause"`.
- Sensing perception (≤ -0.3) → hint contains `"Sensing"` and `"real-world example"`.
- Intuitive perception (≥ +0.3) → hint contains `"Intuitive"` and `"theory"`.
- Neutral (0.0, 0.0) → empty string.
- Within threshold (-0.2, 0.2) → empty string.
- Both dims triggered → hint contains both `"Try It First"` and `"Intuitive"`.

**`TestUnderstandingHints`** (4 tests)
- Sequential (≤ -0.3) → hint contains `"Sequential"` and `"linear"`.
- Global (≥ +0.3) → hint contains `"Big Picture"`.
- Neutral (0.0) → empty string.
- Within threshold (±0.2) → empty string.

Existing 29 tests are unaffected — all new parameters default to `""`.

---

## Design Decisions

1. **Prompt hints, not new agents**: Processing/Perception/Understanding adaptation is purely a prompt-level concern. Adding agents for these would increase latency and complexity with no benefit — the existing Drafter and Integrator already receive all context needed to apply the hints.

2. **`_get_fslsm_dim` vs extending `_get_fslsm_input`**: A new generic extractor avoids modifying the existing `_get_fslsm_input` function (preserving its tested contract) while eliminating code duplication across three dimension reads.

3. **Processing + Perception combined into one hint string**: Both dimensions apply at the same pipeline stage (Drafter) and both control per-section content structure. Combining them into a single injected block keeps the prompt coherent and avoids repeating the `**Learning Style Instructions**` header twice.

4. **Understanding injected into Integrator, not Drafter**: Document-level flow (big-picture intro, sequential transitions, cross-references) is a holistic concern that can only be applied when synthesising the full document. The Integrator is the correct stage.

5. **Backward compatibility**: All new fields and parameters default to `""`. When a score is between -0.3 and +0.3, hint strings are empty and the prompts behave identically to the previous version. Existing callers (non-genmentor path, all previous tests) require no changes.

---

## Verification

| Scenario | Profile values | Expected |
|----------|---------------|----------|
| Active processing | `fslsm_processing = -0.7` | Each drafted section contains a `🔧 Try It First` challenge block |
| Reflective processing | `fslsm_processing = +0.7` | Each drafted section contains a `🤔 Reflection Pause` question |
| Sensing perception | `fslsm_perception = -0.7` | Sections open with real-world example before theory |
| Intuitive perception | `fslsm_perception = +0.7` | Sections open with abstract principle before examples |
| Sequential understanding | `fslsm_understanding = -0.7` | Document has linear flow; "Building on..." transitions; no forward refs |
| Global understanding | `fslsm_understanding = +0.7` | Document starts with `🗺️ Big Picture` section; cross-references present |
| Neutral (all dims) | all = 0.0 | Empty hint strings; output identical to previous pipeline |
| Backward compat | fslsm_input only, no other dims | `_get_fslsm_dim` returns 0.0 for missing keys; hints are empty |

**Unit tests**: `pytest backend/tests/test_adaptive_content_delivery.py -v` → all tests pass (existing 29 + 16 new = 45 total)
