# Tightened Plan: Latency-Aware Content QA with Always-On Final Evaluation and Best-Effort Fallback

## Summary

Implement a decision-complete orchestration that:

- keeps fast deterministic safeguards early,
- batches lightweight LLM checks where safe,
- always runs a final integration LLM evaluation,
- uses targeted repair to limit latency,
- returns best-effort content if final quality still fails,
- and improves media UX by replacing raw source titles with concise display titles plus short grounded descriptions.

This plan resolves previous ambiguity around “quality gate” semantics, section-to-draft mapping, retry budgets, and media-label grounding.

## Terminology and Policy (Locked)

1. **Final integration evaluation is always-on and decisive for repair flow.**
2. **Best-effort fallback remains enabled** (chosen policy): if quality remains unacceptable after retry budget is exhausted, return best-effort content with internal failure classification.
3. Because of (2), we will use the term **“final quality checkpoint”** (not hard gate) in code/docs to avoid contradiction.

## Goals

1. Improve content quality consistency with minimal additional latency.
2. Ensure repair actions are targeted and deterministic when possible.
3. Prevent malformed drafts from contaminating integration.
4. Improve media readability (concise video title + short explanation).
5. Preserve backward compatibility of normal API responses.

## Non-Goals

- No frontend feature redesign.
- No automatic full restart from explorer in this iteration.
- No mandatory exposure of QA metadata in standard API payload.

## End-to-End Flow (Decision Complete)

## 1. Input parse + setup
- Parse incoming profile/path/session.
- Build `session_adaptation_contract`.
- Resolve `lightweight_llm` once.
- Create request-scoped `trace_id` for internal QA events.

## 2. Explore knowledge points
- Existing call, unchanged.

## 3. Draft all knowledge points (parallel)
- Existing call path, unchanged.

## 4. Deterministic strict draft audit (per draft, local)
Run local checks:
- has top-level `##`,
- no empty `##`,
- each `##` has explanatory prose or meaningful `###` subtree with prose,
- no asset-only top-level sections,
- no placeholder-only sections.

### Exception handling
Do not fail solely by word count if section has valid technical instructional structure (code/table-heavy but with explanatory context).

### Output
For each draft:
- `draft_id`
- `deterministic_pass: bool`
- `issues`
- `improvement_directives`

## 5. Batched lightweight draft checkpoint
Evaluate only deterministic-pass drafts via lightweight LLM in batches.

### Batch limits (required)
- `max_batch_drafts`: 6
- `max_batch_chars`: 18_000
- `max_single_draft_chars`: 6_000 (truncate with safe suffix marker for evaluator context)
- If batch call fails: fall back to deterministic verdict for that batch and mark evaluator status `degraded`.

### LLM output per draft
- `is_acceptable`
- `issues`
- `improvement_directives`

## 6. Targeted draft repair
- Retry only failed drafts once (`max_draft_retries=1`).
- Pass binding `evaluator_feedback` back into drafter prompt.
- Re-run deterministic audit + batched evaluator on repaired subset only.

### Draft terminal failure rule
If any draft remains unacceptable:
- classify request state `draft_quality_terminal_failure=true`,
- continue only if `min_acceptable_drafts_ratio >= 0.7` and all required core knowledge points are present,
- otherwise short-circuit to controlled best-effort path using available content with internal severity `HIGH`.

## 7. Media retrieval + combined relevance/label enrichment
Keep retrieval stage unchanged, then run one lightweight combined evaluator on candidates that pass deterministic topical prefilter.

### Combined media evaluator output per resource
- `keep: bool`
- `display_title: str` (concise, learner-facing)
- `short_description: str` (single sentence, 8-24 words)
- `confidence: float` (0-1, optional internal)

### Grounding constraints (strict)
`display_title` and `short_description` must be derived only from:
- original `title`
- `snippet`/`description`
- session title / key topics
No new claims beyond source metadata/topic context.

### Fallback
If LLM fails:
- keep deterministic topical filter behavior,
- derive `display_title` with heuristic title cleaner,
- derive `short_description` from snippet truncation/template.

## 8. Stable section identity mapping (required for selective redraft)
Before integration, create stable objects:
- `draft_id` (immutable, per knowledge point)
- `knowledge_point_id`
- `draft_title`
- `draft_content`

During integration, preserve a mapping table:
- `section_index -> draft_id` (or list of draft_ids if merged)
This mapping must be returned internally by integrator adapter so selective redraft can target correct drafts.

## 9. Integrate document
- Existing integrator call, extended to accept optional `integration_feedback` on retries.

## 10. Final integration quality checkpoint (always-on lightweight LLM)
Always run final evaluator on integrated document.

### Evaluator output
- `is_acceptable`
- `issues`
- `improvement_directives`
- `repair_scope`: one of
  - `integrator_only`
  - `section_redraft`
  - `full_restart_required`
- `affected_section_indices` (optional, must be resolvable through mapping)
- `severity`: `low|medium|high`

## 11. Targeted repair execution
Retry budget:
- `max_integrator_retries=1`
- `max_section_redraft_rounds=1`
- global `max_quality_rounds=3` across final checkpoint attempts.

### Rules
1. If `repair_scope=integrator_only`: rerun integrator once with directives.
2. If `repair_scope=section_redraft`: map `affected_section_indices -> draft_id`, redraft only those drafts, reintegrate once.
3. If `repair_scope=full_restart_required`: do not auto restart in this iteration; proceed to best-effort fallback classification.

After each repair pass, rerun final integration evaluator (always-on).

## 12. Final fallback policy
If still unacceptable after retry budget:
- return best-effort content payload,
- set internal status:
  - `quality_checkpoint_passed=false`
  - `fallback_mode=best_effort`
  - `final_failure_reason`
- keep API success response to preserve UX continuity.

## 13. Audio + quiz generation
Run on final returned document (accepted or best-effort), unchanged from current behavior.

## Public Interfaces / Types

## Public API
No required breaking changes to standard response fields.

## Internal schema additions
1. `DraftQualityRecord`
- `draft_id`
- `deterministic_pass`
- `llm_pass`
- `issues`
- `directives`
- `attempt_count`
- `status`

2. `IntegratedQualityRecord`
- `is_acceptable`
- `issues`
- `directives`
- `repair_scope`
- `affected_section_indices`
- `attempt_count`

3. `MediaResource` internal extension
- `display_title` (optional)
- `short_description` (optional)

4. `OrchestrationQualityTrace`
- `trace_id`
- draft and integration records
- fallback reason and severity
- latency timings by stage

## Prompt and Agent Changes

## A) Draft evaluator prompt/agent
- strict usability framing (not broad essay critique).
- support batched evaluation payload.

## B) Integrator evaluator prompt/agent (new)
- whole-document coherence and learner-fit checkpoint.
- explicit repair scope classification.

## C) Media relevance evaluator prompt/agent
- evolve from boolean-only to boolean + labeling output.
- preserve conservative keep/drop behavior.

## D) Knowledge drafter prompt
- retain strict heading requirements.
- treat evaluator directives as binding on retries.

## Rendering and Parsing Changes

## 1. Media rendering
In inline renderer:
- title precedence: `display_title` then `title`.
- render `short_description` for videos (same style as image description).
Files: [learning_document_integrator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/learning_document_integrator.py)

## 2. Section parser robustness
Replace title-based `find(...)` logic with offset-based heading extraction robust to duplicate titles.
Also ignore headings inside fenced code blocks before section slicing.
Files: [content_view.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/utils/content_view.py)

## Latency Controls

1. Batch draft evaluator with hard chunk limits.
2. Combined media relevance+label call (single pass).
3. Targeted retries only (never broad replay by default).
4. Global round budget and per-stage retry caps.
5. Internal timing metrics captured per stage for p50/p95 monitoring.

## Files to Modify

- [backend/modules/content_generator/orchestrators/content_generation_pipeline.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/orchestrators/content_generation_pipeline.py)
- [backend/modules/content_generator/agents/search_enhanced_knowledge_drafter.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/search_enhanced_knowledge_drafter.py)
- [backend/modules/content_generator/prompts/search_enhanced_knowledge_drafter.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/prompts/search_enhanced_knowledge_drafter.py)
- [backend/modules/content_generator/agents/media_relevance_evaluator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/media_relevance_evaluator.py)
- [backend/modules/content_generator/prompts/media_relevance_evaluator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/prompts/media_relevance_evaluator.py)
- [backend/modules/content_generator/agents/learning_document_integrator.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/agents/learning_document_integrator.py)
- [backend/modules/content_generator/schemas.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/modules/content_generator/schemas.py)
- [backend/utils/content_view.py](/Users/micocomia/Documents/3%20-%20School/Winter%202026/DTI%205902/Repos/Ami/backend/utils/content_view.py)
- New:
  - `backend/modules/content_generator/agents/integrated_document_evaluator.py`
  - `backend/modules/content_generator/prompts/integrated_document_evaluator.py`

## Test Cases and Scenarios

## Draft stage
1. Empty/heading-only/asset-only top sections fail deterministically.
2. Code-heavy but explained section passes deterministic audit.
3. Batch evaluation returns per-draft directives.
4. Only failed drafts retried.
5. Batch evaluator failure triggers deterministic fallback and degraded flag.

## Mapping + selective repair
6. `affected_section_indices` correctly resolve to `draft_id` even with duplicate section titles.
7. Selective redraft updates only mapped drafts.

## Integration checkpoint
8. Final evaluator always runs.
9. Integrator-only repair path works.
10. Section-redraft repair path works.
11. Full-restart-required leads to best-effort fallback (no auto full restart).

## Media enrichment
12. Combined evaluator keeps/rejects correctly.
13. Videos display concise title (`display_title`) and short description.
14. No hallucinated media descriptions outside source/topic context.

## Parser robustness
15. Duplicate `##` titles do not break section boundaries.
16. `##` inside fenced code blocks are ignored as section delimiters.

## Fallback and observability
17. Failed final checkpoint still returns best-effort content.
18. Internal trace contains quality records, attempt counts, and stage latencies.

## Acceptance Criteria

1. Average call count reduced vs unbatched multi-agent alternative.
2. Final integration checkpoint always executed.
3. Targeted repair works without full replay in common failures.
4. Best-effort fallback behavior is explicit and internally observable.
5. Video cards show concise title + short explanation.
6. Section parsing remains correct with repeated headings and code fences.
7. No breaking changes to standard API response schema.

## Assumptions and Defaults

1. Final policy: best-effort return on exhausted retries.
2. Draft retry cap: 1.
3. Integrator retry cap: 1.
4. Selective redraft rounds: 1.
5. Global quality rounds cap: 3.
6. Batch limits:
- max drafts per batch: 6
- max chars per batch: 18,000
- max chars per draft snapshot: 6,000
7. Metadata exposure: internal only by default.
