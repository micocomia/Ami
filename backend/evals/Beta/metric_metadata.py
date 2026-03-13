"""Shared interpretation metadata for Beta evaluation metrics."""

from __future__ import annotations

from copy import deepcopy

CATEGORY_METADATA = {
    "skill_gap": {
        "title": "Skill Gap Quality",
        "current_product_note": (
            "Evaluates the current skill-gap pipeline against the mapper and gap-identifier prompt contracts, "
            "including evidence restrictions and retrieval-aware calibration."
        ),
        "mvp_change_note": (
            "Metric names are mostly unchanged, but Beta now interprets them using the stricter current prompt "
            "rules around allowed evidence and retrieved-context grounding."
        ),
    },
    "plan": {
        "title": "Learning Plan Quality",
        "current_product_note": (
            "Evaluates the current planner against explicit no-skip SOLO progression, mandatory outcome coverage, "
            "and FSLSM structural contracts."
        ),
        "mvp_change_note": (
            "Beta keeps the MVP metric names, but planning metrics now reflect hard scheduler contracts and "
            "deterministic SOLO auditing instead of purely stylistic judgment."
        ),
    },
    "content": {
        "title": "Content Quality",
        "current_product_note": (
            "Evaluates current content generation against the selected session contract, adaptation cues, "
            "SOLO-aware depth, and quiz-design rules."
        ),
        "mvp_change_note": (
            "Metric names remain stable, but Beta judges content against current contract-preservation rules rather "
            "than generic long-form instructional writing preferences."
        ),
    },
    "rag": {
        "title": "Tutor RAG Quality",
        "current_product_note": (
            "Evaluates the tutor short-answer retrieval flow, emphasizing grounded concise answers and verified "
            "course-context retrieval."
        ),
        "mvp_change_note": (
            "The metric names are the same RAGAS metrics, but the evaluated product path changed from MVP’s "
            "drafting/product-mode RAG to the tutor short-answer flow, so direct score comparison is not valid."
        ),
    },
    "api_perf": {
        "title": "API Performance",
        "current_product_note": "Reports latency/error behavior for the current backend endpoints.",
        "mvp_change_note": (
            "Perf remains the most comparable category, but endpoint composition changed because content generation "
            "is now a single endpoint and tutor RAG is evaluated separately."
        ),
    },
}

METRIC_METADATA = {
    "skill_gap": {
        "completeness": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now grounded in retrieved course context when available.",
            "assessment_change_reason": (
                "The current skill mapper prompt treats retrieved course content as the primary evidence source for "
                "skill selection and required-level calibration."
            ),
            "prompt_basis": [
                "skill_requirement_mapper: retrieved_context is primary evidence when present",
                "skill_gap_identifier: skill gaps must be grounded in provided requirements and goal",
            ],
        },
        "gap_calibration": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now explicitly constrained by allowed-evidence rules.",
            "assessment_change_reason": (
                "The current gap identifier forbids using FSLSM, motivation, or generic intent statements as "
                "evidence of current proficiency."
            ),
            "prompt_basis": [
                "skill_gap_identifier: allowed/disallowed evidence policy",
                "skill_gap_identifier: transferable evidence rule",
            ],
        },
        "confidence_validity": {
            "comparable_to_mvp": "yes",
            "assessment_change_vs_mvp": "Same metric name, but confidence is checked against the stricter evidence policy.",
            "assessment_change_reason": (
                "The current gap identifier defines explicit confidence thresholds tied to evidence quality."
            ),
            "prompt_basis": [
                "skill_gap_identifier: confidence mapping rules",
            ],
        },
        "expert_calibration": {
            "comparable_to_mvp": "yes",
            "assessment_change_vs_mvp": "Same core meaning with clearer SOLO grounding.",
            "assessment_change_reason": (
                "The current prompts define expert as extended-abstract transfer and explicitly discourage inflation "
                "from broad but shallow evidence."
            ),
            "prompt_basis": [
                "skill_requirement_mapper: SOLO required_level mapping",
                "skill_gap_identifier: SOLO current_level mapping",
            ],
        },
        "solo_level_accuracy": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now checks SOLO levels against stricter evidence and transfer rules.",
            "assessment_change_reason": (
                "The current prompts define detailed SOLO mappings and anti-collapse logic for technical backgrounds."
            ),
            "prompt_basis": [
                "skill_gap_identifier: SOLO reasoning and anti-collapse check",
            ],
        },
    },
    "plan": {
        "pedagogical_sequencing": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now bounded by deterministic no-skip SOLO progression checks.",
            "assessment_change_reason": (
                "The current scheduler prompt makes one-step SOLO progression a hard requirement, and the planner "
                "already has a deterministic auditor for violations."
            ),
            "prompt_basis": [
                "learning_path_scheduling: no SOLO level skipping",
                "plan_feedback: SOLO correctness handled by deterministic auditor",
            ],
        },
        "skill_coverage": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now requires full stepwise coverage and exact outcome-name coverage.",
            "assessment_change_reason": (
                "The current scheduler requires every in-progress skill to appear verbatim in desired outcomes and "
                "to progress one level at a time until the required level is reached."
            ),
            "prompt_basis": [
                "learning_path_scheduling: mandatory outcome coverage",
                "learning_path_scheduling: skill name consistency",
            ],
        },
        "scope_appropriateness": {
            "comparable_to_mvp": "yes",
            "assessment_change_vs_mvp": "Core meaning unchanged.",
            "assessment_change_reason": (
                "This still measures whether the path matches the learner’s goal and background, though it is now "
                "read alongside the stricter sequencing and coverage rules."
            ),
            "prompt_basis": [
                "learning_path_scheduling: goal-oriented and personalized directives",
            ],
        },
        "session_abstraction_quality": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now includes abstract-to-flag consistency, not just abstract polish.",
            "assessment_change_reason": (
                "The current scheduler prompt makes checkpoint, reflection, sequence-hint, and input-mode wording "
                "in the abstract a hard consistency requirement."
            ),
            "prompt_basis": [
                "learning_path_scheduling: abstract-flag consistency",
            ],
        },
        "fslsm_structural_alignment": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now checks explicit structural FSLSM fields and their abstract realization.",
            "assessment_change_reason": (
                "The current planner prompt maps numeric FSLSM dimensions to concrete session flags, order hints, "
                "navigation mode, and input-mode hints."
            ),
            "prompt_basis": [
                "learning_path_scheduling: FSLSM-driven structure",
                "plan_feedback: FSLSM dimensions are the authoritative style source",
            ],
        },
        "solo_outcome_progression": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now judged with deterministic legality evidence instead of free-form interpretation.",
            "assessment_change_reason": (
                "The current planner defines exact legal transitions and forbids same-level repeats except remediation."
            ),
            "prompt_basis": [
                "learning_path_scheduling: progression rules",
                "plan_feedback_simulator: deterministic SOLO audit",
            ],
        },
    },
    "content": {
        "cognitive_level_match": {
            "comparable_to_mvp": "yes",
            "assessment_change_vs_mvp": "Same metric name with more explicit session-contract grounding.",
            "assessment_change_reason": (
                "The current content pipeline ties depth to session outcomes, knowledge-point SOLO levels, and the "
                "learner profile rather than generic difficulty."
            ),
            "prompt_basis": [
                "goal_oriented_knowledge_explorer: assign SOLO target level",
                "search_enhanced_knowledge_drafter: respect knowledge_point.solo_level",
            ],
        },
        "factual_accuracy": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now explicitly checks source-supported drafting and citation preservation.",
            "assessment_change_reason": (
                "The current drafter and integrator prompts make external resources primary and forbid unsupported facts."
            ),
            "prompt_basis": [
                "search_enhanced_knowledge_drafter: external_resources are primary source of truth",
                "learning_document_integrator: preserve citations",
            ],
        },
        "quiz_alignment": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now checks quiz-type SOLO mapping rather than generic quiz quality only.",
            "assessment_change_reason": (
                "The current quiz generator explicitly maps question types to SOLO levels and document-only grounding."
            ),
            "prompt_basis": [
                "document_quiz_generator: SOLO-aligned question design",
            ],
        },
        "engagement_quality": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now rewards contract-appropriate engagement cues instead of output length or flourish.",
            "assessment_change_reason": (
                "The current content prompts encode engagement through checkpoint challenges, reflection pauses, "
                "application/theory order, and media-mode fit."
            ),
            "prompt_basis": [
                "search_enhanced_knowledge_drafter: honor processing/perception/input/understanding contract",
                "learning_document_integrator: preserve adaptation cues",
            ],
        },
        "fslsm_content_adaptation": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now checks preservation of contract-driven adaptation cues throughout the content pipeline.",
            "assessment_change_reason": (
                "The current content system encodes FSLSM adaptation in the session contract, draft structure, and integrator behavior."
            ),
            "prompt_basis": [
                "search_enhanced_knowledge_drafter: contract-driven adaptation requirements",
                "learning_document_integrator: processing/perception/input preservation",
            ],
        },
        "solo_cognitive_alignment": {
            "comparable_to_mvp": "partial",
            "assessment_change_vs_mvp": "Now checks SOLO alignment across knowledge points and quizzes, not just prose depth.",
            "assessment_change_reason": (
                "The current content pipeline distributes SOLO expectations across knowledge exploration, drafting, and assessment."
            ),
            "prompt_basis": [
                "goal_oriented_knowledge_explorer: per-point solo_level",
                "document_quiz_generator: SOLO-aligned question design",
            ],
        },
    },
    "rag": {
        "context_precision": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Same RAGAS metric, different product path.",
            "assessment_change_reason": "Beta evaluates tutor short-answer grounding rather than MVP’s product-mode drafting flow.",
            "prompt_basis": ["ai_chatbot_tutor: concise grounded tutoring with preloaded context"],
        },
        "context_recall": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Same RAGAS metric, different answer style and retrieval objective.",
            "assessment_change_reason": "The tutor is optimized for concise grounded help, not exhaustive draft-style retrieval coverage.",
            "prompt_basis": ["ai_chatbot_tutor: short synthesis of retrieved lecture material"],
        },
        "faithfulness": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Same metric name, tutor answers are shorter and grounded differently.",
            "assessment_change_reason": "Beta answers are evaluated against tutor constraints and retrieved session/course context.",
            "prompt_basis": ["ai_chatbot_tutor: answer primarily from preloaded context"],
        },
        "answer_relevancy": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Same metric name, but measured on tutor-style short answers.",
            "assessment_change_reason": "The current tutor prompt prioritizes concise, learner-centered responses over draft-style completeness.",
            "prompt_basis": ["ai_chatbot_tutor: concise, warm, adaptive tutoring reply"],
        },
        "answer_correctness": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Same metric name, but grounded in the tutor path.",
            "assessment_change_reason": "Current correctness depends on the tutor retrieval flow and short-answer synthesis behavior.",
            "prompt_basis": ["ai_chatbot_tutor: grounded course-specific answers before answering"],
        },
        "metadata_course_hit_rate": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now reflects tutor retrieval metadata rather than old drafting metadata.",
            "assessment_change_reason": "The metadata trace now comes from the tutor retrieval path.",
            "prompt_basis": ["ai_chatbot_tutor: structured goal-context retrieval grounding"],
        },
        "metadata_verified_source_rate": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now reflects tutor retrieval metadata rather than old drafting metadata.",
            "assessment_change_reason": "Verified-source reporting is tied to tutor retrieval traces in Beta.",
            "prompt_basis": ["ai_chatbot_tutor: retrieval_trace contexts"],
        },
        "metadata_keyword_coverage": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now interpreted in concise-answer mode.",
            "assessment_change_reason": "Beta answers are intentionally shorter, so keyword coverage reflects a different product tradeoff.",
            "prompt_basis": ["ai_chatbot_tutor: prefer short synthesis over broad tutorial answer"],
        },
        "metadata_fact_coverage_answer": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now reflects concise tutor answers rather than knowledge drafts.",
            "assessment_change_reason": "The answer style changed materially between MVP and Beta.",
            "prompt_basis": ["ai_chatbot_tutor: answer primarily from preloaded context"],
        },
        "metadata_fact_coverage_context": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now reflects tutor retrieval traces.",
            "assessment_change_reason": "Context evidence comes from tutor retrieval_trace rather than draft-stage retrieval.",
            "prompt_basis": ["ai_chatbot_tutor: retrieval_trace contexts"],
        },
        "metadata_expected_lecture_hit_rate": {
            "comparable_to_mvp": "no",
            "assessment_change_vs_mvp": "Now reflects tutor goal-context retrieval instead of draft retrieval.",
            "assessment_change_reason": "Lecture-hit reporting is tied to tutor metadata in Beta.",
            "prompt_basis": ["ai_chatbot_tutor: structured goal-context retrieval grounding"],
        },
    },
}


def get_category_metadata(category: str) -> dict:
    return deepcopy(CATEGORY_METADATA.get(category, {}))


def get_metric_metadata(category: str, metrics: list[str] | None = None) -> dict:
    category_metrics = deepcopy(METRIC_METADATA.get(category, {}))
    if metrics is None:
        return category_metrics
    return {metric: category_metrics[metric] for metric in metrics if metric in category_metrics}


def comparable_metrics_for(category: str, include_partial: bool = True) -> list[str]:
    allowed = {"yes", "partial"} if include_partial else {"yes"}
    return [
        metric
        for metric, meta in METRIC_METADATA.get(category, {}).items()
        if meta.get("comparable_to_mvp") in allowed
    ]
