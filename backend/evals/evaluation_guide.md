# Evaluation Interpretation Guide (MVP)

This guide summarizes the current evaluation setup used to compare:
- `GenMentor` (baseline)
- `5902Group5` (enhanced)

It is designed for presentation use: what goes in, what is measured, and what comes out.

## 1) Inputs: Profiles, Goals, Scenarios

### Dataset source
- `5902Group5/backend/evals/datasets/shared_test_cases.json`

### Learning goals (`learning_goals`)
- `G1`: Full-stack web development (React + Node.js)
- `G2`: Topics in MIT `6.0001` (Introduction to CS and Python)
- `G3`: Build/deploy REST API to cloud
- `G4`: Project management (intentionally vague to test refinement behavior)

### Learner profile inputs
Two profile-context strings are provided per scenario to match real frontend/backend behavior:
- `learner_information_genmentor`: occupation + background text
- `learner_information_enhanced`: persona label/description + background text

Enhanced scenarios also include persona + FSLSM fields:
- `persona_enhanced`
- `fslsm_enhanced` (`processing`, `perception`, `input`, `understanding`)

### Background archetypes present in MVP scenarios
- `B1`: Complete beginner
- `B2`: Intermediate self-taught developer
- `B3`: Career switcher
- `B4`: Junior professional beginner (PM)
- `B5`: Technical specialist transitioning to PM

### Scenario set (MVP balanced subset)
8 scenarios total, 2 per goal:
- `S1`: `G1`, `B1`, Balanced
- `S2`: `G1`, `B3`, Visual
- `S3`: `G2`, `B2`, Hands-on Explorer
- `S4`: `G2`, `B1`, Balanced
- `S5`: `G3`, `B1`, Balanced
- `S6`: `G3`, `B2`, Hands-on Explorer
- `S7`: `G4`, `B4`, Balanced, `goal_is_vague=true`
- `S8`: `G4`, `B5`, Visual, `goal_is_vague=true`

Why this is balanced enough for MVP:
- Equal goal coverage (2 each)
- Persona diversity (Balanced / Hands-on / Visual)
- Includes vague-goal PM cases to expose auto-refinement differences

### RAG test inputs
- Standard RAG cases: 8 knowledge points (2 per goal)
- Metadata RAG cases: 3 explicit course-code cases (`6.0001`) in `rag_metadata_cases`
- Product asymmetry for validity:
  - Enhanced is evaluated in product mode with access to pre-ingested verified course corpus.
  - Baseline is evaluated in product mode with web-search-driven retrieval only.
  - No additional ingestion is performed by the eval script.

## 2) Evaluations and Rubrics

## A. Skill Gap Evaluation
- Script: `5902Group5/backend/evals/eval_skill_gap.py`
- Core endpoint under evaluation: `/identify-skill-gap-with-info`
- Judge type: LLM-as-a-judge, `1-5` scale per metric

### Shared metrics (both systems)
- `completeness`: coverage of required skill areas
- `gap_calibration`: plausibility of current/required levels from learner background
- `goal_refinement_quality`: specificity/actionability of refined goal
- `confidence_validity`: whether confidence labels match evidence quality

### Enhanced-only metrics
- `expert_calibration`: correct usage/withholding of expert level
- `solo_level_accuracy`: SOLO level fit to learner evidence

### Mini ablation added
A third variant is computed:
- `genmentor_forced_refine`: baseline with explicit `/refine-learning-goal` before skill-gap identification

This helps separate:
- baseline default behavior
- refinement-only uplift
- other enhanced-system uplift

### Rubric explicitness
All metrics have explicit score anchors for `1,2,3,4,5` in prompt text.

## B. Learning Plan Evaluation
- Script: `5902Group5/backend/evals/eval_plan.py`
- Pipeline evaluated:
  - `/identify-skill-gap-with-info`
  - `/create-learner-profile-with-info`
  - `/schedule-learning-path`
- Judge type: LLM-as-a-judge, `1-5`

### Shared metrics
- `pedagogical_sequencing`
- `skill_coverage`
- `scope_appropriateness`
- `session_abstraction_quality`

### Enhanced-only metrics
- `fslsm_structural_alignment`
- `solo_outcome_progression`

### Rubric explicitness
All metrics have explicit score anchors for `1,2,3,4,5`.

### Zero-gap handling
If a scenario yields `0` identified skill gaps, plan/content rows are marked:
- `not_applicable_reason = "zero_skill_gaps"`
- excluded from metric averaging
- counted in summary via `not_applicable_zero_gap_count`

## C. Content Evaluation
- Script: `5902Group5/backend/evals/eval_content.py`
- Pipeline evaluated (session 1 only for cost control):
  - `/identify-skill-gap-with-info`
  - `/create-learner-profile-with-info`
  - `/schedule-learning-path`
  - `/explore-knowledge-points`
  - `/draft-knowledge-points`
  - `/integrate-learning-document`
  - `/generate-document-quizzes`
- Judge type: LLM-as-a-judge, `1-5`

### Shared metrics
- `cognitive_level_match`
- `factual_accuracy`
- `quiz_alignment`
- `engagement_quality`

### Enhanced-only metrics
- `fslsm_content_adaptation`
- `solo_cognitive_alignment`

### Important alignment note
The judge now uses Stage-1 explored knowledge points (frontend-consistent) as the "Knowledge Points Covered" context.

### Rubric explicitness
All metrics have explicit score anchors for `1,2,3,4,5`.

## D. RAG Evaluation
- Script: `5902Group5/backend/evals/eval_rag.py`
- Drafting endpoint used for evaluation: `/draft-knowledge-points` (single-item list)
- Automatic metrics: RAGAS (`0-1` scale)

### Core RAGAS metrics
- `context_precision`
- `context_recall`
- `faithfulness`
- `answer_relevancy`

### Split reporting
- overall (`all cases`)
- `standard_*` metrics (standard cases only)
- `metadata_*` metrics (metadata-targeted cases only)

### Metadata diagnostics (non-RAGAS)
- `metadata_course_hit_rate`
- `metadata_verified_source_rate`
- `metadata_keyword_coverage`
- `metadata_case_count`

### Product-mode metadata preflight (enhanced)
Included in RAG summary to make run assumptions explicit:
- `evaluation_mode = "product_asymmetric"`
- `assumption = "enhanced_has_verified_course_content__baseline_web_search"`
- `verified_preflight` (object with probe/hit counts)
- `verified_preflight_passed` (boolean)

## E. API Performance Evaluation
- Script: `5902Group5/backend/evals/eval_api_perf.py`
- Measures latency + error behavior across pipeline endpoints

### Endpoint-level outputs
For each endpoint:
- `p50_ms`
- `p95_ms`
- `error_rate_pct`
- `sample_count`
- `applicable_count`
- `skipped_count` (dependency-skipped downstream calls)

### Resume/checkpoint support
- Cache path default: `backend/evals/results/api_perf_checkpoint.json`
- Resume flags available in `eval_api_perf.py` and `run_all.py`

## 3) Expected Evaluation Outputs

## Per-eval JSON artifacts
- Skill gap: `5902Group5/backend/evals/results/skill_gap_results.json`
  - keys: `results`, `summary`
  - summary versions: `genmentor`, `genmentor_forced_refine`, `enhanced`

- Plan: `5902Group5/backend/evals/results/plan_results.json`
  - keys: `results`, `summary`

- Content: `5902Group5/backend/evals/results/content_results.json`
  - keys: `results`, `summary`

- RAG: `5902Group5/backend/evals/results/rag_results.json`
  - keys: `raw_rows`, `summary`

- API perf: `5902Group5/backend/evals/results/api_perf_results.json`
  - keys by version: `raw_runs`, `summary`

## Combined run artifacts (`run_all.py`)
- JSON: `5902Group5/backend/evals/results/comparison_report.json`
  - includes summaries for all eval categories
- Markdown: `5902Group5/backend/evals/results/comparison_report.md`
  - presentation-friendly comparison tables

### Report sections you should expect
- RAG: overall + standard-only + metadata-only + metadata diagnostics
- Skill gap: baseline vs enhanced + mini ablation table
- Learning plan: shared + enhanced-only metrics
- Content: shared + enhanced-only metrics
- API performance: latency table + error-rate table
- Overall shared-dimension average summary
