# Comparative Evaluation Report
*Generated: 2026-02-20 15:24:53*

GenMentor = baseline | 5902Group5 = enhanced

## 1. RAG Quality (RAGAS, 0–1 scale, Product Mode)

*Method note: enhanced has verified-course-content access; baseline is web-search driven.*

### Overall

| Metric | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| context_precision | N/A | 0.79 | — |
| context_recall | N/A | 0.47 | — |
| faithfulness | N/A | 0.74 | — |
| answer_relevancy | N/A | 0.83 | — |

### Standard Cases Only

| Metric | GenMentor | 5902Group5 | Delta |
|---|---|---|---|

### Metadata Cases Only

| Metric | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| context_precision | N/A | 0.79 | — |
| context_recall | N/A | 0.47 | — |
| faithfulness | N/A | 0.74 | — |
| answer_relevancy | N/A | 0.83 | — |

### Metadata Diagnostics

| Metric | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| metadata_course_hit_rate | N/A | 1.00 | — |
| metadata_verified_source_rate | N/A | 1.00 | — |
| metadata_keyword_coverage | N/A | 0.64 | — |
| metadata_fact_coverage_answer | N/A | 0.47 | — |
| metadata_fact_coverage_context | N/A | 0.20 | — |
| metadata_expected_lecture_hit_rate | N/A | 0.67 | — |

## 2. Skill Gap Quality (LLM-Judge, 1–5 scale)

| Dimension | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| completeness | 3.62 | 4.12 | +0.50 |
| gap_calibration | 4.75 | 4.88 | +0.13 |
| goal_refinement_quality | 3.50 | 4.00 | +0.50 |
| confidence_validity | 4.62 | 4.75 | +0.13 |
| expert_calibration *(enhanced only)* | N/A | 5.00 | — |
| solo_level_accuracy *(enhanced only)* | N/A | 4.75 | — |

### Skill-Gap Mini Ablation (Baseline vs Forced Refine vs Enhanced)

| Dimension | GenMentor | GenMentor (Forced Refine) | 5902Group5 |
|---|---|---|---|
| completeness | 3.62 | 4.62 | 4.12 |
| gap_calibration | 4.75 | 4.88 | 4.88 |
| goal_refinement_quality | 3.50 | 4.00 | 4.00 |
| confidence_validity | 4.62 | 4.75 | 4.75 |

## 3. Learning Plan Quality (LLM-Judge, 1–5 scale)

| Dimension | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| pedagogical_sequencing | 5.00 | 5.00 | +0.00 |
| skill_coverage | 4.75 | 4.75 | +0.00 |
| scope_appropriateness | 4.38 | 4.50 | +0.12 |
| session_abstraction_quality | 5.00 | 5.00 | +0.00 |
| fslsm_structural_alignment *(enhanced only)* | N/A | 4.25 | — |
| solo_outcome_progression *(enhanced only)* | N/A | 4.75 | — |

## 4. Content Quality (LLM-Judge, 1–5 scale)

| Dimension | GenMentor | 5902Group5 | Delta |
|---|---|---|---|
| cognitive_level_match | 4.86 | 4.50 | -0.36 |
| factual_accuracy | 5.00 | 5.00 | +0.00 |
| quiz_alignment | 5.00 | 5.00 | +0.00 |
| engagement_quality | 4.14 | 4.00 | -0.14 |
| fslsm_content_adaptation *(enhanced only)* | N/A | 4.12 | — |
| solo_cognitive_alignment *(enhanced only)* | N/A | 4.50 | — |

## 5. API Performance (Latency in ms)

| Endpoint | GenMentor p50 | GenMentor p95 | 5902Group5 p50 | 5902Group5 p95 | p50 Delta |
|---|---|---|---|---|---|
| chat_with_tutor | 10947.9 | 15613.6 | 12585.2 | 16154.3 | +1637 |
| create_learner_profile | 6858.9 | 8288.9 | 6100.7 | 7241.4 | -758 |
| draft_knowledge_points | 53347.3 | 71194.6 | 38073.5 | 65635.9 | -15274 |
| explore_knowledge_points | 1489.6 | 2739.0 | 1862.2 | 2158.3 | +373 |
| generate_document_quizzes | 6486.2 | 8246.4 | 6517.5 | 7558.0 | +31 |
| identify_skill_gap | 7755.0 | 10235.8 | 9081.5 | 10621.9 | +1326 |
| integrate_learning_document | 15002.3 | 20672.0 | 60785.0 | 91589.3 | +45783 |
| refine_learning_goal | 1232.7 | 1858.1 | 1384.3 | 1648.3 | +152 |
| schedule_learning_path | 9179.1 | 18522.4 | 14711.4 | 18828.5 | +5532 |

### Error Rates

| Endpoint | GenMentor error% | 5902Group5 error% |
|---|---|---|
| chat_with_tutor | 0.0% | 0.0% |
| create_learner_profile | 0.0% | 0.0% |
| draft_knowledge_points | 25.0% | 0.0% |
| explore_knowledge_points | 0.0% | 0.0% |
| generate_document_quizzes | 0.0% | 0.0% |
| identify_skill_gap | 0.0% | 0.0% |
| integrate_learning_document | 0.0% | 0.0% |
| refine_learning_goal | 0.0% | 0.0% |
| schedule_learning_path | 0.0% | 0.0% |

---
## Overall Summary

| Version | Shared-Dimension Average (1–5) |
|---|---|
| GenMentor (Baseline) | 4.55 |
| 5902Group5 (Enhanced) | 4.62 |
| Delta | +0.07 |
