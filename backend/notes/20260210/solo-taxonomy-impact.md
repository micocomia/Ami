# SOLO Taxonomy Impact on Ami Agents

## Overview

The current system uses a 4-tier linear proficiency taxonomy (`unlearned`, `beginner`, `intermediate`, `advanced`) across all modules. Replacing this with the SOLO (Structure of the Observed Learning Outcome) taxonomy introduces 5 levels that describe the *quality and structure* of understanding rather than a generic label:

| SOLO Level | Description | Current/Proposed Equivalent |
|------------|-------------|--------------------|
| Prestructural | No relevant understanding | `unlearned` |
| Unistructural | One relevant aspect grasped | `beginner` |
| Multistructural | Multiple aspects known, not yet integrated | `intermediate` |
| Relational | Aspects integrated into a coherent whole | `advanced` |
| Extended Abstract | Can generalize and transfer to new contexts | `expert` |

---

## Impact by Agent

### 1. Skill Requirement Mapper

- **Current behavior**: Maps a learning goal to skills with a `required_level` of beginner/intermediate/advanced.
- **With SOLO**: Required levels become unistructural/multistructural/relational/extended_abstract. The mapper can set more precise targets — e.g., a goal like "apply machine learning to business problems" clearly requires *relational* understanding (integration), not just "advanced."

### 2. Skill Gap Identifier

- **Current behavior**: Compares `current_level` vs `required_level` using ordinal ranking. Gap exists when current < required.
- **With SOLO**: Same ordinal comparison logic, extended to 5 levels. The `reason` field gains richer vocabulary — instead of "learner is at beginner level," the agent can say "learner identifies individual concepts but does not connect them (unistructural)." The gap between multistructural and relational (knowing facts vs. integrating them) becomes an explicit, identifiable transition.

### 3. Adaptive Learner Profiler

- **Current behavior**: Categorizes skills as mastered or in-progress based on current vs. required proficiency. Updates proficiency after sessions.
- **With SOLO**: Proficiency updates become qualitatively meaningful. Moving from multistructural to relational is not just "going up one level" — it represents the learner demonstrating integration of concepts. The profiler's chain-of-thought prompts can reason about the *nature* of the learner's understanding (e.g., "quiz responses show recall of multiple facts but no ability to explain relationships — remains multistructural").

### 4. Learning Path Scheduler

- **Current behavior**: Sequences sessions from "foundational to advanced" and sets `desired_outcome_when_completed` with beginner/intermediate/advanced targets.
- **With SOLO**: Session sequencing gains pedagogical precision. The scheduler can plan explicit transitions:
  - Sessions 1-2: Build unistructural understanding (isolated concepts)
  - Sessions 3-4: Reach multistructural (accumulate multiple aspects)
  - Session 5: Target relational (integrate and connect)
  - Session 6: Target extended_abstract (generalize to new problems)
- The hardest cognitive leap — multistructural to relational — can be given dedicated sessions rather than being glossed over in a "intermediate to advanced" jump.
- The 5th level (extended_abstract) enables capstone sessions focused on transfer and generalization, which the current 3-level system cannot represent.

### 5. Goal-Oriented Knowledge Explorer

- **Current behavior**: Classifies knowledge points as foundational/practical/strategic based on the learner's profile.
- **With SOLO**: Knowledge type selection becomes aligned with the target SOLO transition for the session:
  - Unistructural target: Emphasize **foundational** points (single concepts to grasp)
  - Multistructural target: Mix of **foundational** + **practical** (accumulate and apply)
  - Relational target: Emphasize **practical** points (force integration through application)
  - Extended_abstract target: Emphasize **strategic** points (require generalization)
- The ratio of knowledge types per session becomes a deliberate pedagogical choice rather than an implicit one.

### 6. Search-Enhanced Knowledge Drafter

- **Current behavior**: Tailors content depth based on learner preferences (concise vs. detailed).
- **With SOLO**: Content *structure* changes, not just depth:
  - Unistructural: Present one key idea with a concrete example
  - Multistructural: List and describe multiple related concepts
  - Relational: Use compare/contrast, cause-effect structures to show connections
  - Extended_abstract: Present novel applications, cross-domain analogies, encourage hypothesis
- This gives the LLM explicit guidance on *how* to organize explanations to scaffold the target cognitive structure.

### 7. Learning Document Integrator

- **Current behavior**: Organizes content by knowledge type (foundational -> practical -> strategic) and synthesizes into a cohesive document.
- **With SOLO**: The document flow can mirror the SOLO progression within a single session — start with isolated concepts, accumulate them, then explicitly connect them. Transition sentences between sections can be designed to model integration (the relational step) rather than just being smooth connectors.

### 8. Document Quiz Generator

- **Current behavior**: Adjusts difficulty vaguely ("more foundational questions for beginners, more strategic/complex questions for advanced learners").
- **With SOLO**: Each question can be designed to test a specific SOLO level:
  - **Unistructural**: Recall a single fact or definition -> True/False, Single-choice
  - **Multistructural**: Identify multiple correct facts without integration -> Multiple-choice
  - **Relational**: Explain *why* or *how* concepts connect -> Short-answer ("Explain how X relates to Y")
  - **Extended Abstract**: Apply to a novel scenario -> Short-answer ("Given new situation Z, how would you...")
- The existing four question types (single-choice, multiple-choice, true/false, short-answer) already map naturally to SOLO levels. The quiz generator can target the learner's current SOLO level and one above, creating assessments in the zone of proximal development.
- Quiz results become diagnostic: if a learner passes multistructural questions but fails relational ones, the system knows exactly where the cognitive gap is.

### 9. Learner Feedback Simulator

- **Current behavior**: Evaluates "progression" (logical flow and difficulty scaling), "engagement," and "personalization" qualitatively.
- **With SOLO**: The "progression" dimension becomes concrete and measurable. The simulator can identify specific SOLO-level gaps in the path (e.g., "Session 3 targets relational understanding but Session 2 only reaches unistructural — a multistructural stepping stone is missing"). This makes feedback actionable rather than subjective.

---

## Files Requiring Changes

| File | Change |
|------|--------|
| `modules/adaptive_learner_modeling/schemas.py` | `CurrentLevel` and `RequiredLevel` enums -> SOLO levels |
| `modules/skill_gap_identification/schemas.py` | `LevelCurrent`, `LevelRequired` enums -> SOLO levels; update gap validation ordering |
| `modules/personalized_resource_delivery/schemas.py` | `Proficiency` enum -> SOLO levels |
| `modules/adaptive_learner_modeling/prompts.py` | Explain SOLO semantics in system/task prompts |
| `modules/skill_gap_identification/prompts/skill_requirement_mapper.py` | Update level definitions to SOLO |
| `modules/skill_gap_identification/prompts/skill_gap_identifier.py` | Update level definitions and inference guidance |
| `modules/personalized_resource_delivery/prompts/learning_path_scheduling.py` | SOLO-based session progression directives |
| `modules/personalized_resource_delivery/prompts/goal_oriented_knowledge_explorer.py` | Link knowledge types to target SOLO levels |
| `modules/personalized_resource_delivery/prompts/document_quiz_generator.py` | SOLO-aligned question design guidance |
| `modules/personalized_resource_delivery/prompts/search_enhanced_knowledge_drafter.py` | SOLO-based content structuring |
| `modules/personalized_resource_delivery/prompts/learning_document_integrator.py` | SOLO-aware document flow |
| `modules/personalized_resource_delivery/prompts/learner_feedback_simulation.py` | SOLO-aware progression evaluation |
| Database / stored profiles | Migration from old labels to SOLO labels |
