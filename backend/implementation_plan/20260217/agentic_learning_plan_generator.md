# Backend: Agentic Learning Plan Generator

## Context

The learning plan generator previously operated as a simple LLM call (no tools, no retrieval, manual user-driven refinement). The skill gap agents already follow a mature agentic pattern with retrieval tools, auto-refinement loops, and goal assessment. This plan upgrades the learning plan generator to match that pattern, adding three capabilities:

1. **Course content retrieval** -- ground learning plans in verified syllabus/lecture content
2. **Automated learner simulation + refinement** -- replace manual "Refine Plan" with an automated evaluate-then-refine loop (max 2 refinements)
3. **Adaptive plan regeneration** -- detect major preference/mastery changes and reason about whether to adjust future sessions or regenerate the plan

## Changes Made

### Step 1: Shared Tools Refactor

- Created `modules/tools/` directory with shared tools:
  - `course_content_retrieval_tool.py` (copied from skill_gap/tools/)
  - `learner_simulation_tool.py` (copied from learning_plan_generator/tools/)
  - `plan_regeneration_tool.py` (new)
- Updated imports in `skill_gap/agents/skill_requirement_mapper.py` and `learning_plan_generator/tools/__init__.py`

### Step 2: Course Content Retrieval in Learning Path Scheduler

- Updated `LearningPathScheduler.__init__()` to accept `search_rag_manager` and `retrieved_docs_sink`
- Conditionally attaches `create_course_content_retrieval_tool` (same pattern as SkillRequirementMapper)
- Updated system prompt with retrieval instructions (syllabus first, fallback to lectures, max 3 calls)
- Updated `schedule_learning_path_with_llm()` and `reschedule_learning_path_with_llm()` to accept and pass `search_rag_manager`, now return `(plan, retrieved_sources)` tuples
- Updated `main.py` endpoints to pass `search_rag_manager` and include `retrieved_sources` in response

### Step 3: Agentic Plan Generation with Auto-Refinement

- Added `_evaluate_plan_quality()` deterministic quality gate (keyword-based heuristic + suggestion count)
- Added `schedule_learning_path_agentic()` orchestration function:
  - Generates initial plan with retrieval
  - Evaluates via learner simulator (gpt-4o-mini, fast path)
  - Runs deterministic quality gate
  - Refines via `reflexion()` if quality fails (max 2 refinements)
  - Returns plan + metadata (iterations, evaluation, sources)
- Added `POST /schedule-learning-path-agentic` endpoint
- Deprecated `/refine-learning-path`, `/iterative-refine-path` (kept for backward compat)

### Step 4: Adaptive Plan Regeneration

- Created `modules/tools/plan_regeneration_tool.py`:
  - `compute_fslsm_deltas()` -- absolute deltas between old and new FSLSM dims
  - `count_mastery_failures()` -- count non-mastered sessions
  - `decide_regeneration()` -- deterministic keep/adjust/regenerate decision
    - KEEP: abs delta < 0.3 on ALL dims AND all mastery on track
    - ADJUST_FUTURE: any dim delta in [0.3, 0.5) OR single mastery failure
    - REGENERATE: any dim delta >= 0.5 OR multiple mastery failures
- Added `POST /adapt-learning-path` endpoint
- Updated `POST /evaluate-mastery` to include `plan_adaptation_suggested` flag

### Step 5: Unit Tests

- `tests/test_plan_quality_gate.py` (7 tests) -- deterministic quality gate
- `tests/test_plan_regeneration.py` (13 tests) -- FSLSM deltas, mastery failures, decision logic
- `tests/test_agentic_learning_plan.py` (8 tests) -- dedup sources, scheduler init, metadata structure
- All 32 new tests pass

## Latency Budget

| Operation | Model | Expected Latency | Guardrail |
|-----------|-------|-----------------|-----------|
| Initial plan generation | Main LLM (gpt-4o) | ~5-8s | recursion_limit=25 |
| Course content retrieval | Embedding + ChromaDB | ~0.5s per call | Max 3 calls |
| Learner simulation | gpt-4o-mini | ~2-3s | use_ground_truth=False |
| Deterministic quality gate | None (pure function) | ~0ms | Instant |
| Plan refinement (if needed) | Main LLM (gpt-4o) | ~5-8s | Max 2 refinements |
| Regeneration decision | Deterministic | ~0ms | Mostly deterministic |
| **Worst case total** | | **~22-28s** | **Hard cap at 3 plan generations** |
| **Best case (pass first try)** | | **~8-12s** | |

## Files Modified

### Backend
- `modules/tools/__init__.py` (new)
- `modules/tools/course_content_retrieval_tool.py` (new, copy)
- `modules/tools/learner_simulation_tool.py` (new, copy)
- `modules/tools/plan_regeneration_tool.py` (new)
- `modules/learning_plan_generator/agents/learning_path_scheduler.py` (modified)
- `modules/learning_plan_generator/agents/__init__.py` (modified)
- `modules/learning_plan_generator/tools/__init__.py` (modified)
- `modules/learning_plan_generator/prompts/learning_path_scheduling.py` (modified)
- `modules/skill_gap/agents/skill_requirement_mapper.py` (modified)
- `main.py` (modified)
- `tests/test_plan_quality_gate.py` (new)
- `tests/test_plan_regeneration.py` (new)
- `tests/test_agentic_learning_plan.py` (new)
