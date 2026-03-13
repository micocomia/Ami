# Beta Evaluation Report
*Generated: 2026-03-13 11:03:51*

Ami Backend (Current)

Beta is the canonical scorecard for the current backend. Metric names are retained where possible, but their interpretation follows the current module prompt contracts.

Interpretation guide: `/Users/micocomia/Documents/3 - School/Winter 2026/DTI 5902/Repos/Ami/backend/evals/Beta/evaluation_guide.md`

## Current Product Scorecard

## 1. RAG Quality (RAGAS, 0-1 scale)

Evaluates the tutor short-answer retrieval flow, emphasizing grounded concise answers and verified course-context retrieval.

Assessment changed vs MVP: The metric names are the same RAGAS metrics, but the evaluated product path changed from MVP’s drafting/product-mode RAG to the tutor short-answer flow, so direct score comparison is not valid.

| Metric | Score |
|---|---|
| context_precision | 0.78 |
| context_recall | 0.52 |
| faithfulness | 0.70 |
| answer_relevancy | 0.86 |
| answer_correctness | 0.65 |
| metadata_course_hit_rate | 1.00 |
| metadata_verified_source_rate | 1.00 |
| metadata_keyword_coverage | 0.55 |
| metadata_fact_coverage_answer | 0.22 |
| metadata_fact_coverage_context | 0.28 |
| metadata_expected_lecture_hit_rate | 1.00 |

| Metric | Comparable to MVP? | Assessment Change in Beta | Why |
|---|---|---|---|
| context_precision | no | Same RAGAS metric, different product path. | Beta evaluates tutor short-answer grounding rather than MVP’s product-mode drafting flow. |
| context_recall | no | Same RAGAS metric, different answer style and retrieval objective. | The tutor is optimized for concise grounded help, not exhaustive draft-style retrieval coverage. |
| faithfulness | no | Same metric name, tutor answers are shorter and grounded differently. | Beta answers are evaluated against tutor constraints and retrieved session/course context. |
| answer_relevancy | no | Same metric name, but measured on tutor-style short answers. | The current tutor prompt prioritizes concise, learner-centered responses over draft-style completeness. |
| answer_correctness | no | Same metric name, but grounded in the tutor path. | Current correctness depends on the tutor retrieval flow and short-answer synthesis behavior. |
| metadata_course_hit_rate | no | Now reflects tutor retrieval metadata rather than old drafting metadata. | The metadata trace now comes from the tutor retrieval path. |
| metadata_verified_source_rate | no | Now reflects tutor retrieval metadata rather than old drafting metadata. | Verified-source reporting is tied to tutor retrieval traces in Beta. |
| metadata_keyword_coverage | no | Now interpreted in concise-answer mode. | Beta answers are intentionally shorter, so keyword coverage reflects a different product tradeoff. |
| metadata_fact_coverage_answer | no | Now reflects concise tutor answers rather than knowledge drafts. | The answer style changed materially between MVP and Beta. |
| metadata_fact_coverage_context | no | Now reflects tutor retrieval traces. | Context evidence comes from tutor retrieval_trace rather than draft-stage retrieval. |
| metadata_expected_lecture_hit_rate | no | Now reflects tutor goal-context retrieval instead of draft retrieval. | Lecture-hit reporting is tied to tutor metadata in Beta. |

## 2. Skill Gap Quality (LLM-Judge, 1-5 scale)

Evaluates the current skill-gap pipeline against the mapper and gap-identifier prompt contracts, including evidence restrictions and retrieval-aware calibration.

Assessment changed vs MVP: Metric names are mostly unchanged, but Beta now interprets them using the stricter current prompt rules around allowed evidence and retrieved-context grounding.

| Dimension | Score |
|---|---|
| completeness | 4.00 |
| gap_calibration | 4.38 |
| confidence_validity | 4.12 |
| expert_calibration | 4.25 |
| solo_level_accuracy | 4.38 |
| scenario_count | 8 |
| scored_scenario_count | 8 |
| error_count | 0 |

| Metric | Comparable to MVP? | Assessment Change in Beta | Why |
|---|---|---|---|
| completeness | partial | Now grounded in retrieved course context when available. | The current skill mapper prompt treats retrieved course content as the primary evidence source for skill selection and required-level calibration. |
| gap_calibration | partial | Now explicitly constrained by allowed-evidence rules. | The current gap identifier forbids using FSLSM, motivation, or generic intent statements as evidence of current proficiency. |
| confidence_validity | yes | Same metric name, but confidence is checked against the stricter evidence policy. | The current gap identifier defines explicit confidence thresholds tied to evidence quality. |
| expert_calibration | yes | Same core meaning with clearer SOLO grounding. | The current prompts define expert as extended-abstract transfer and explicitly discourage inflation from broad but shallow evidence. |
| solo_level_accuracy | partial | Now checks SOLO levels against stricter evidence and transfer rules. | The current prompts define detailed SOLO mappings and anti-collapse logic for technical backgrounds. |

## 3. Learning Plan Quality (LLM-Judge, 1-5 scale)

Evaluates the current planner against explicit no-skip SOLO progression, mandatory outcome coverage, and FSLSM structural contracts.

Assessment changed vs MVP: Beta keeps the MVP metric names, but planning metrics now reflect hard scheduler contracts and deterministic SOLO auditing instead of purely stylistic judgment.

| Dimension | Score |
|---|---|
| pedagogical_sequencing | 3.75 |
| skill_coverage | 3.38 |
| scope_appropriateness | 4.25 |
| session_abstraction_quality | 3.50 |
| fslsm_structural_alignment | 3.50 |
| solo_outcome_progression | 3.75 |
| scenario_count | 8 |
| scored_scenario_count | 8 |
| not_applicable_zero_gap_count | 0 |
| error_count | 0 |

| Deterministic Plan Audit | Count |
|---|---|
| total_violation_count | 8 |
| total_coverage_gap_count | 12 |
| scenarios_with_violations | 3 |
| scenarios_with_coverage_gaps | 4 |
| scenarios_with_flag_inconsistencies | 6 |

| Metric | Comparable to MVP? | Assessment Change in Beta | Why |
|---|---|---|---|
| pedagogical_sequencing | partial | Now bounded by deterministic no-skip SOLO progression checks. | The current scheduler prompt makes one-step SOLO progression a hard requirement, and the planner already has a deterministic auditor for violations. |
| skill_coverage | partial | Now requires full stepwise coverage and exact outcome-name coverage. | The current scheduler requires every in-progress skill to appear verbatim in desired outcomes and to progress one level at a time until the required level is reached. |
| scope_appropriateness | yes | Core meaning unchanged. | This still measures whether the path matches the learner’s goal and background, though it is now read alongside the stricter sequencing and coverage rules. |
| session_abstraction_quality | partial | Now includes abstract-to-flag consistency, not just abstract polish. | The current scheduler prompt makes checkpoint, reflection, sequence-hint, and input-mode wording in the abstract a hard consistency requirement. |
| fslsm_structural_alignment | partial | Now checks explicit structural FSLSM fields and their abstract realization. | The current planner prompt maps numeric FSLSM dimensions to concrete session flags, order hints, navigation mode, and input-mode hints. |
| solo_outcome_progression | partial | Now judged with deterministic legality evidence instead of free-form interpretation. | The current planner defines exact legal transitions and forbids same-level repeats except remediation. |

## 4. Content Quality (LLM-Judge, 1-5 scale)

Evaluates current content generation against the selected session contract, adaptation cues, SOLO-aware depth, and quiz-design rules.

Assessment changed vs MVP: Metric names remain stable, but Beta judges content against current contract-preservation rules rather than generic long-form instructional writing preferences.

| Dimension | Score |
|---|---|
| cognitive_level_match | 4.50 |
| factual_accuracy | 5.00 |
| quiz_alignment | 4.62 |
| engagement_quality | 4.00 |
| fslsm_content_adaptation | 4.38 |
| solo_cognitive_alignment | 4.50 |
| scenario_count | 8 |
| scored_scenario_count | 8 |
| not_applicable_zero_gap_count | 0 |
| error_count | 0 |

| Metric | Comparable to MVP? | Assessment Change in Beta | Why |
|---|---|---|---|
| cognitive_level_match | yes | Same metric name with more explicit session-contract grounding. | The current content pipeline ties depth to session outcomes, knowledge-point SOLO levels, and the learner profile rather than generic difficulty. |
| factual_accuracy | partial | Now explicitly checks source-supported drafting and citation preservation. | The current drafter and integrator prompts make external resources primary and forbid unsupported facts. |
| quiz_alignment | partial | Now checks quiz-type SOLO mapping rather than generic quiz quality only. | The current quiz generator explicitly maps question types to SOLO levels and document-only grounding. |
| engagement_quality | partial | Now rewards contract-appropriate engagement cues instead of output length or flourish. | The current content prompts encode engagement through checkpoint challenges, reflection pauses, application/theory order, and media-mode fit. |
| fslsm_content_adaptation | partial | Now checks preservation of contract-driven adaptation cues throughout the content pipeline. | The current content system encodes FSLSM adaptation in the session contract, draft structure, and integrator behavior. |
| solo_cognitive_alignment | partial | Now checks SOLO alignment across knowledge points and quizzes, not just prose depth. | The current content pipeline distributes SOLO expectations across knowledge exploration, drafting, and assessment. |

## 5. API Performance (Latency in ms)

Reports latency/error behavior for the current backend endpoints.

Assessment changed vs MVP: Perf remains the most comparable category, but endpoint composition changed because content generation is now a single endpoint and tutor RAG is evaluated separately.

| Endpoint | p50 | p95 | error% | applicable_count | skipped_count |
|---|---|---|---|---|---|
| chat_with_tutor | 3145.70 | 4086.30 | 0.00 | 8 | 0 |
| create_learner_profile | 7890.80 | 13516.80 | 0.00 | 8 | 0 |
| generate_learning_content | 83637.30 | 186797.90 | 0.00 | 8 | 0 |
| identify_skill_gap | 17369.20 | 27899.40 | 0.00 | 8 | 0 |
| refine_learning_goal | 1354.40 | 1574.90 | 0.00 | 8 | 0 |
| schedule_learning_path | 14951.30 | 25137.80 | 0.00 | 8 | 0 |

## Bridge Comparison to MVP

Only metrics marked `yes` or `partial` are included here. This is a continuity view, not a claim that Beta should preserve MVP raw scores across changed product behaviors.

| Category | Bridge Metrics Included |
|---|---|
| Skill Gap | completeness, gap_calibration, confidence_validity, expert_calibration, solo_level_accuracy |
| Learning Plan | pedagogical_sequencing, skill_coverage, scope_appropriateness, session_abstraction_quality, fslsm_structural_alignment, solo_outcome_progression |
| Content | cognitive_level_match, factual_accuracy, quiz_alignment, engagement_quality, fslsm_content_adaptation, solo_cognitive_alignment |
| RAG | none |

---
## Overall Summary

| Metric | Score |
|---|---|
| current_product_average | 4.14 |
| bridge_subset_average | 4.13 |