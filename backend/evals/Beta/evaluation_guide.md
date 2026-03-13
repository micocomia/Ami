# Evaluation Interpretation Guide (Beta)

This guide explains how the Beta suite evaluates the **current backend**.

Unlike MVP, Beta is not a direct system-vs-system comparison. It is the canonical scorecard for the current backend, and each metric is interpreted against the current module prompt contracts.

## Current Product Principle

Beta evaluates the current backend against the rules encoded in these prompt families:
- `skill_gap`
- `learner_profiler`
- `learning_plan_generator`
- `content_generator`
- `ai_chatbot_tutor`

Metric names are kept where possible for continuity, but unchanged names do **not** imply unchanged semantics.

## Interpretation Rules by Category

### Skill Gap
- `gap_calibration` and `solo_level_accuracy` now follow the current allowed-evidence policy.
- Retrieved course content is treated as primary evidence when present.

### Learning Plan
- `pedagogical_sequencing` and `skill_coverage` are no longer purely stylistic judgments.
- The planner has explicit no-skip SOLO progression and mandatory outcome coverage rules.
- Beta therefore combines LLM judgment with deterministic plan-audit signals.

### Content
- Content is evaluated against the selected session contract, not only against generic prose quality.
- FSLSM alignment now means preserving checkpoint/reflection/order/input-mode cues across drafting and integration.
- Quiz alignment now includes the current quiz-type-to-SOLO design rules.

### RAG
- Beta RAG evaluates the tutor short-answer flow.
- MVP RAG evaluated a different backend path and is not directly comparable.
- Lower tutor recall can reflect a deliberate concise-answer and latency tradeoff rather than a simple quality regression.

## MVP Comparability

Each Beta metric is labeled:
- `yes`: meaning is close enough to compare cautiously to MVP
- `partial`: same name, but interpretation changed materially
- `no`: not meaningfully comparable because the evaluated product behavior changed

The Markdown and JSON reports surface these labels together with:
- how the assessment changed from MVP
- why it changed
- which prompt contracts the metric is aligned to
