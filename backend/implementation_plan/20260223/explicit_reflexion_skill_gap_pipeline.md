# Explicit Reflexion Architecture for Skill Gap Pipeline

## Context

The previous skill gap pipeline used LangChain `@tool` decorators for two core decisions:

1. **`SkillRequirementMapper`** — used a `retrieve_course_content` tool, delegating all retrieval decisions (which course, which lecture, how many calls) to the LLM. This made parsing natural language references like "Lesson 4" vs "Lecture 4" vs "Week 4" fragile and non-deterministic.

2. **`SkillGapIdentifier`** — used an `assess_goal_quality` tool to determine if the goal was vague and whether the learner had mastered all skills. Whether the tool was called at all was up to the LLM, creating inconsistent `goal_assessment` fields in the response.

Additionally, the auto-refinement loop mixed goal clarification logic with skill gap quality evaluation in a single `range(2)` loop with no clean separation, making it hard to reason about which concerns triggered which behaviour.

This plan replaces the tool-based pattern with an **explicit two-loop reflexion architecture** where each loop has a single, clearly defined responsibility.

---

## Architecture

### Two-Loop Design

```
original_goal = learning_goal
was_auto_refined = False
lightweight_llm = LLMFactory.create(model="gpt-4o-mini")

# ── LOOP 1: Goal Clarification (GoalContextParser ↔ LearningGoalRefiner) ────
# All goal-related decisions happen here and only here.
MAX_GOAL_ITERATIONS = 2

FOR attempt IN range(MAX_GOAL_ITERATIONS):
  goal_context = GoalContextParser(lightweight_llm).parse({
      "learning_goal": learning_goal, "learner_information": learner_information
  })
  # → {course_code, lecture_number, content_category, page_number, is_vague}

  retrieved_docs = _retrieve_context_for_goal(goal_context, search_rag_manager)

  IF NOT goal_context["is_vague"]:
    BREAK

  IF attempt < MAX_GOAL_ITERATIONS - 1:
    refined = LearningGoalRefiner(lightweight_llm).refine_goal(...)
    IF refined_goal != learning_goal:
      learning_goal = refined_goal; was_auto_refined = True
    ELSE:
      BREAK  # refiner returned same goal; no further progress

# Map requirements ONCE (with finalized goal + retrieved context)
effective_requirements = SkillRequirementMapper(llm).map_goal_to_skill(
    {"learning_goal": learning_goal}, retrieved_context=retrieved_context_str
)

# ── LOOP 2: Skill Gap Reflexion (SkillGapIdentifier ↔ SkillGapEvaluator) ────
# Evaluator assesses skill gap quality only — no goal refinement here.
MAX_EVAL_ITERATIONS = 2
evaluator_feedback = ""

FOR iteration IN range(MAX_EVAL_ITERATIONS):
  skill_gaps_result = SkillGapIdentifier(llm).identify_skill_gap(
      {...}, retrieved_context=retrieved_context_str,
      evaluator_feedback=evaluator_feedback
  )

  IF iteration < MAX_EVAL_ITERATIONS - 1:
    evaluation = SkillGapEvaluator(lightweight_llm).evaluate({...})
    IF evaluation["is_acceptable"]:
      BREAK
    evaluator_feedback = evaluation["feedback"]

# ── POST-LOOP ────────────────────────────────────────────────────────────────
# all_mastered computed deterministically (with vacuous truth guard)
gaps_list = skill_gaps_result.get("skill_gaps", [])
all_mastered = bool(gaps_list) AND all(not g["is_gap"] for g in gaps_list)

skill_gaps_result["goal_assessment"] = {is_vague, all_mastered, requires_retrieval, ...}
skill_gaps_result["retrieved_sources"] = _deduplicate_sources(retrieved_docs)
skill_gaps_result["bias_audit"] = BiasAuditor(lightweight_llm).audit_skill_gaps(...)
```

### Lightweight Model Usage

All supporting agents use `gpt-4o-mini` (fast, low cost). The main `llm` parameter is reserved for the two high-stakes agents:

| Agent | Model | Calls (worst case) |
|---|---|---|
| `GoalContextParser` | `gpt-4o-mini` | 2 |
| `LearningGoalRefiner` | `gpt-4o-mini` | 1 |
| `SkillRequirementMapper` | main LLM | 1 |
| `SkillGapIdentifier` | main LLM | 2 |
| `SkillGapEvaluator` | `gpt-4o-mini` | 1 |
| `BiasAuditor` | `gpt-4o-mini` | 1 |
| **Total** | | **≤ 8 calls** |

Happy path (not vague, first gaps accepted): 5 calls total.

---

## Changes Made

### New Agents

#### `GoalContextParser` (`modules/skill_gap/agents/goal_context_parser.py`)

Lightweight LLM-based extraction of structured goal metadata:
- `course_code` — e.g., "6.0001", "DTI5902"
- `lecture_number` — handles all natural language variants ("Lesson 4", "Week 4", "Session 4", "Module 4")
- `content_category` — "Lectures", "Exercises", "Syllabus", "References"
- `page_number` — for PDF-level precision
- `is_vague` — assessed relative to the learner's background (e.g., "learn Python" + senior ML engineer → vague; "learn Python for data analysis" → not vague)

Replaces the regex-based lecture number extraction that was fragile for natural language variations.

#### `SkillGapEvaluator` (`modules/skill_gap/agents/skill_gap_evaluator.py`)

Lightweight critic for skill gap quality only (no goal assessment):
- `is_acceptable: bool` — True when gaps are correct, complete, and well-justified
- `issues: List[str]` — specific problems (e.g., "Python Basics marked expert with low confidence")
- `feedback: str` — direct instruction to the identifier for revision

Deliberately excludes `needs_goal_refinement` — goal decisions are entirely Loop 1's responsibility.

### Updated Agents

#### `SkillGapIdentifier` (`modules/skill_gap/agents/skill_gap_identifier.py`)

Full rewrite:
- **`SkillGapPayload`** — added `retrieved_context: str` and `evaluator_feedback: str` as optional Pydantic fields (follows BiasAuditor serialization pattern; no post-validation injection)
- **`__init__`** — removed `search_rag_manager` parameter and tool creation; always `tools=None`
- **`identify_skill_gap()`** — validates all inputs through schema, then `json.dumps()` for `skill_requirements` before passing to prompt
- **Module-level helpers** (new):
  - `_retrieve_context_for_goal(goal_context, search_rag_manager)` — deterministic retrieval using parsed context parameters; calls `retrieve_filtered()` with all four metadata filters
  - `_format_retrieved_docs(docs)` — formats up to 5 docs as `[Source N: file_name]\ncontent` strings
  - `_deduplicate_sources(docs)` — deduplicates by `(file_name, lecture_number)` key
- **`identify_skill_gap_with_llm()`** — full two-loop rewrite replacing the old `range(2)` loop

#### `SkillRequirementMapper` (`modules/skill_gap/agents/skill_requirement_mapper.py`)

- Removed `search_rag_manager` and `retrieved_docs_sink` parameters from `__init__`; removed tool creation
- **`Goal2SkillPayload`** — added `retrieved_context: str = Field(default="")`
- **`map_goal_to_skill()`** — accepts `retrieved_context: str = ""` keyword arg; passes `payload.model_dump()` directly to `invoke()` (all fields are strings)
- **`map_goal_to_skills_with_llm()`** — removed `search_rag_manager` parameter

### Updated Prompts

#### `prompts/skill_gap_identifier.py`

- Removed tool-calling instructions ("if assess_goal_quality tool is available…")
- `goal_assessment` field changed from optional to **REQUIRED — never null**
- Added `{retrieved_context}` section to task prompt (pre-fetched course content)
- Added `{evaluator_feedback}` section to task prompt (empty on first pass)

#### `prompts/skill_requirement_mapper.py`

- Replaced multi-paragraph retrieval tool instructions with a single `**Using Retrieved Content**` directive
- Added `{retrieved_context}` section to task prompt

### Updated Schemas

#### `schemas.py` — `GoalAssessment`

Added `requires_retrieval: bool = Field(default=False)` — indicates whether verified course content was found and used for skill assessment.

### Updated Infrastructure

#### `base/verified_content_manager.py` — `retrieve_filtered()`

Added `page_number: Optional[int] = None` as a native filter parameter, following the same pattern as the existing `lecture_number` filter. Enables the `GoalContextParser` to pass `page_number=5` and get page-precise retrieval results without post-filtering.

---

## Files Created

| File | Description |
|------|-------------|
| `modules/skill_gap/agents/goal_context_parser.py` | New GoalContextParser agent |
| `modules/skill_gap/prompts/goal_context_parser.py` | System + task prompts for GoalContextParser |
| `modules/skill_gap/agents/skill_gap_evaluator.py` | New SkillGapEvaluator agent |
| `modules/skill_gap/prompts/skill_gap_evaluator.py` | System + task prompts for SkillGapEvaluator |

## Files Modified

| File | Change |
|------|--------|
| `base/verified_content_manager.py` | Added `page_number` native filter to `retrieve_filtered()` |
| `modules/skill_gap/agents/skill_gap_identifier.py` | Full rewrite — two-loop orchestration, new helpers, updated payload |
| `modules/skill_gap/prompts/skill_gap_identifier.py` | Removed tool instructions; added `{retrieved_context}`, `{evaluator_feedback}` |
| `modules/skill_gap/agents/skill_requirement_mapper.py` | Removed tool pattern; `Goal2SkillPayload` updated with `retrieved_context` |
| `modules/skill_gap/prompts/skill_requirement_mapper.py` | Removed tool instructions; added `{retrieved_context}` |
| `modules/skill_gap/schemas.py` | Added `requires_retrieval` to `GoalAssessment` |
| `modules/skill_gap/tools/__init__.py` | Removed deleted tool imports |
| `modules/tools/__init__.py` | Removed `course_content_retrieval_tool` export (no remaining consumers) |

## Files Deleted

| File | Reason |
|------|--------|
| `modules/skill_gap/tools/goal_assessment_tool.py` | Replaced by `GoalContextParser` + inline post-loop logic |
| `modules/skill_gap/tools/course_content_retrieval_tool.py` | Replaced by `_retrieve_context_for_goal` helper |

---

## Tests

### `tests/test_skill_gap_orchestrator.py` (full replacement)

| Class | Tests | Coverage |
|---|---|---|
| `TestLoop1GoalClarification` | 4 | Vague goal triggers refiner; clear goal skips Loop 1; max iterations respected; same goal returned breaks |
| `TestLoop2SkillGapReflexion` | 3 | Evaluator accepts first pass; evaluator rejects then accepts (feedback propagated); max iterations respected |
| `TestPostLoop` | 4 | BiasAuditor always runs; all_mastered detection; goal_assessment always present; Loop 2 never calls refiner |

### `tests/test_skill_gap_tools.py` (updated)

| Class | Tests | Coverage |
|---|---|---|
| `TestGoalContextParser` | 7 | Course + lecture extraction; exercises category; page_number; generic vague; background-aware vague; specific domain; schema validation |
| `TestRetrieveContextForGoal` | 5 | No manager; no VCM; `retrieve_filtered` called with correct params; `page_number` passthrough; fallback to `retrieve` |
| `TestSkillGapEvaluator` | 4 | Returns is_acceptable; returns feedback on rejection; no `needs_goal_refinement` field; schema validation |
| `TestGoalRefinementTool` | 4 | Unchanged from previous sprint |

All 393 backend tests pass.

---

## Verification

```bash
# Target test files
cd backend && python -m pytest tests/test_skill_gap_orchestrator.py tests/test_skill_gap_tools.py -v

# Full regression suite
cd backend && python -m pytest tests/ -v
```

**Manual checks:**

1. `"Lesson 4 of 6.0001"` and `"Lecture 4 of 6.0001"` → identical result; `is_vague=False`; lecture 4 content retrieved
2. `"What is on page 5 of lecture 4 of 6.0001?"` → `page_number=5` passed as native filter to `retrieve_filtered`
3. `"Show me the exercises from Lesson 3 of DTI5902"` → `content_category="Exercises"` used in retrieval
4. `"learn Python"` + any background → `is_vague=True`; refiner called; re-parsed; Loop 2 proceeds
5. `"learn Python for data analysis"` → `is_vague=False`; refiner never called; mapper + Loop 2 proceed
6. Evaluator rejects initial gaps → identifier called again with `evaluator_feedback`; accepted on second pass
7. Evaluator always rejects → loop exits after `MAX_EVAL_ITERATIONS`; no goal refinement triggered
8. All-mastered goal → `goal_assessment.all_mastered=True` with suggestion; BiasAuditor still runs
9. `POST /identify-skill-gap-with-info` response includes `bias_audit`, `goal_assessment`, `retrieved_sources` at top level
