# FSLSM Tight Integration (Remaining Dimensions) — Frontend

**Date**: 2026-02-18
**Sprint**: 3 — Agentic Content Generator
**Branch**: `sprint-3-agentic-content-generator`

---

## Context

Sprint 2 added FSLSM adaptations at the **learning path level** (mastery lock, checkpoint challenges, module maps, narrative overviews, session sequencing hints). Sprint 3 extends the integration to the **document content level** for the three FSLSM dimensions that previously had no content-level effect:

| Dimension | Score | What gets injected into the document |
|-----------|-------|--------------------------------------|
| Processing | ≤ -0.3 (Active) | 🔧 **Try It First** — hands-on challenge before explanation |
| Processing | ≥ +0.3 (Reflective) | 🤔 **Reflection Pause** — deep-thinking question |
| Perception | ≤ -0.3 (Sensing) | Content ordered: concrete example → facts → theory |
| Perception | ≥ +0.3 (Intuitive) | Content ordered: abstract principle → patterns → examples |
| Understanding | ≤ -0.3 (Sequential) | Strict linear order; explicit "Next, …" transitions |
| Understanding | ≥ +0.3 (Global) | 🗺️ **Big Picture** overview section; cross-references between concepts |

All adaptations are implemented as **prompt-level hints** injected into the backend's drafting and integration agents. The document the frontend receives is already adapted — there are no new API fields and no new frontend rendering logic required.

**Depends on:** `backend/implementation_plan/20260218/fslsm_tight_integration_content_generator.md`

---

## 1. Frontend Impact Assessment

### 1A. No new API calls

The hints are injected inside the existing `draft-knowledge-points` and `integrate-learning-document` pipeline stages. The frontend calls these endpoints identically to before — no new parameters, no new endpoints.

### 1B. No new rendering logic

All hint markers (`🔧`, `🤔`, `🗺️`) and reordered sections are embedded in the document markdown returned by the backend. The existing `st.markdown(..., unsafe_allow_html=True)` call in `render_document_content_by_section()` renders them correctly:

- Emoji headings (`### 🔧 Try It First`) render as styled `h3` elements.
- Bold call-out text (`**🤔 Reflection Pause:**`) renders inline.
- The `## 🗺️ Big Picture` section appears as a normal paginated section in the TOC sidebar.

### 1C. Section pagination compatibility

`render_document_content_by_section()` splits the document on `##`-level headings. New FSLSM-injected `##` sections (e.g., `## 🗺️ Big Picture`) are automatically included in the paginated view and the sidebar TOC — no special handling needed.

### 1D. Existing path-level indicators still apply

The learning path adaptations from Sprint 2 continue to function alongside the new content-level hints. They address different aspects:

| Layer | Sprint | Example |
|-------|--------|---------|
| Path structure | Sprint 2 | Session locked until previous mastered |
| Session metadata | Sprint 2 | "Contains Checkpoint Challenges" caption on card |
| Document content | Sprint 3 | 🔧 Try It First block inside document |

No conflict exists — they are additive.

---

## 2. User-Facing Verification Points

Although no code changes are required, the QA team should verify that content-level FSLSM adaptation is working end-to-end by observing the rendered document.

### 2A. Processing dimension

| Persona | fslsm_processing | Expected document feature |
|---------|-----------------|--------------------------|
| Hands-on Explorer | -0.7 (active) | Document opens with a `### 🔧 Try It First` challenge block |
| Reflective Reader | +0.7 (reflective) | Document contains a `### 🤔 Reflection Pause` callout |
| Balanced Learner | 0.0 | Neither block present |

### 2B. Perception dimension

| Persona | fslsm_perception | Expected document feature |
|---------|-----------------|--------------------------|
| Hands-on Explorer | -0.5 (sensing) | Section starts with a concrete worked example before theory |
| Conceptual Thinker | +0.7 (intuitive) | Section opens with the abstract principle, examples appear later |

### 2C. Understanding dimension

| Persona | fslsm_understanding | Expected document feature |
|---------|---------------------|--------------------------|
| Reflective Reader | +0.5 (global) | First section is `## 🗺️ Big Picture`; subsequent sections cross-reference each other |
| Hands-on Explorer | -0.3 (sequential) | Sections follow strict order with explicit transitions ("Next, we will…") |

---

## 3. Flow 6 User Flows Update

The user flows test plan (`docs/user_flows_test_plan.md`) has been updated with **sub-test 6.6** covering these content-level FSLSM adaptations. No changes to `test_fslsm_overrides.py` are required (those tests cover path-level logic). The new `test_adaptive_content_delivery.py` backend tests (16 hint-injection tests) cover the content-level behaviour.

---

## Implementation Order

| Step | What | Files | Notes |
|------|------|-------|-------|
| 1 | *(none)* | — | All adaptation is backend-side prompt injection |
| 2 | Update user flows test plan | `docs/user_flows_test_plan.md` | Sub-test 6.6 added; backend test file referenced |

No frontend source files were modified for this feature.

---

## Verification

1. **Active processing** (Hands-on Explorer): Generate session content. Verify a "🔧 Try It First" block appears near the start of the first content section. Block presents a hands-on task _before_ the explanation.
2. **Reflective processing** (Reflective Reader): Generate session content. Verify a "🤔 Reflection Pause" question block appears within the document.
3. **Sensing perception** (Hands-on Explorer): Verify the document begins with a concrete worked example (code snippet, real-world scenario) and introduces formal terminology only afterwards.
4. **Intuitive perception** (Conceptual Thinker): Verify the document opens with the abstract principle or pattern, with concrete examples appearing in later subsections.
5. **Sequential understanding** (sequential persona): Verify no section refers forward to a concept not yet introduced. Explicit transition phrases present.
6. **Global understanding** (Conceptual Thinker): Verify the first `##` section is titled with "Big Picture" or equivalent overview. Later sections contain cross-references.
7. **Neutral learner** (Balanced Learner, all scores near 0): Verify none of the special markers appear — document reads as a standard structured article.
