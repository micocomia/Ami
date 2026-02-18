# Backend: Agentic Skill Gap Pipeline

## Context
The skill gap agents currently rely entirely on LLM knowledge — no retrieval, no autonomy, no self-correction. We're making them genuinely agentic with a self-correcting pipeline:
- **SkillRequirementMapper** autonomously retrieves course content (syllabus first, then lectures) to ground skill requirements
- **SkillGapIdentifier** autonomously assesses goal quality (vague? all mastered?) via a tool
- **Goal refinement becomes automatic** — if a goal is vague and enough context exists, the system refines it without user intervention
- **Latency guardrails** throughout to keep response times reasonable

---

## 1. Create course content retrieval tool
**NEW**: `modules/skill_gap/tools/__init__.py` + `modules/skill_gap/tools/course_content_retrieval_tool.py`

`@tool("retrieve_course_content")` with factory pattern (like `learner_simulation_tool`):
- Input: `query`, `content_category` (optional: "Syllabus"/"Lectures"/"Exercises"/"References"), `lecture_number` (optional), `k`
- Uses `VerifiedContentManager.retrieve()` + in-memory metadata filtering on `content_category` and `lecture_number` (already present in indexed docs via `base/verified_content_loader.py`)
- Returns `format_docs()` string from `base/search_rag.py`
- Reusable by learning plan generator agent later

## 2. Create goal assessment tool
**NEW**: `modules/skill_gap/tools/goal_assessment_tool.py`

`@tool("assess_goal_quality")`:
- Input: `learning_goal: str`, `skill_gaps: Optional[List[Dict]]`
- Checks vagueness via retrieval (no relevant content found → likely vague)
- Checks all-mastered from skill_gaps (`all(not g["is_gap"] for g in skill_gaps)`)
- Returns: `{"is_vague": bool, "all_mastered": bool, "suggestion": str}`
- Reusable by any agent that needs goal quality assessment

## 3. Create goal refinement tool
**NEW**: `modules/skill_gap/tools/goal_refinement_tool.py`

`@tool("refine_learning_goal")`:
- Input: `learning_goal: str`, `learner_information: str`, `course_context: str`
- Wraps the existing `LearningGoalRefiner` agent (`modules/skill_gap/agents/learning_goal_refiner.py`) — calls `refine_goal()` internally
- Returns: `{"refined_goal": str, "was_refined": bool, "refinement_reason": str}`
- Uses a **fast/small model** (e.g., gpt-4o-mini) for the refinement call to minimize latency
- This replaces the manual "AI Refinement" button flow

## 4. Make SkillRequirementMapper a tool-calling agent

**How it works**: `create_agent` (LangGraph) handles tool calls in an internal loop — the agent calls tools, gets results, reasons, repeats. `BaseAgent.invoke()` extracts `response['messages'][-1].content` which is the final answer after all tool calls. JSON parsing in `utils/llm_output.py` works unchanged on this final output.

**`modules/skill_gap/agents/skill_requirement_mapper.py`**:
- Accept `search_rag_manager: Optional[SearchRagManager]` in constructor
- If `search_rag_manager` provided with a `verified_content_manager`, create retrieval tool via `create_course_content_retrieval_tool(search_rag_manager)`
- Pass `tools=[retrieve_tool]` to `super().__init__()` (or `tools=None` if no search_rag_manager)
- Update `Goal2SkillPayload` — no change needed (goal is still the only input)
- Update `map_goal_to_skills_with_llm()` to accept and pass `search_rag_manager`

**`modules/skill_gap/prompts/skill_requirement_mapper.py`**:
- Update system prompt to instruct the agent to use `retrieve_course_content`:
  - **First**: Query with `content_category="Syllabus"` to get course-level skill requirements
  - **Then**: If goal references specific content (e.g., "lecture 3", "slide 8"), query with `content_category="Lectures"` and appropriate `lecture_number`
  - **Iterate**: If results insufficient, reformulate query (max 3 tool calls)
  - **Fall back**: If no relevant content found, use own knowledge
- Keep `{learning_goal}` in task prompt (no `{course_context}` placeholder needed — agent retrieves on its own)

## 5. Make SkillGapIdentifier a tool-calling agent

**`modules/skill_gap/schemas.py`**:
- New `GoalAssessment` model:
  ```python
  class GoalAssessment(BaseModel):
      is_vague: bool = False
      all_mastered: bool = False
      suggestion: str = ""
      auto_refined: bool = False
      original_goal: str = ""
  ```
- Add `goal_assessment` field to `SkillGaps` with `default_factory=GoalAssessment` (backward-compatible)

**`modules/skill_gap/agents/skill_gap_identifier.py`**:
- Accept `search_rag_manager: Optional[SearchRagManager]` in constructor
- Create goal assessment tool via `create_goal_assessment_tool(search_rag_manager)`
- Pass `tools=[assess_tool]` to `super().__init__()`
- Agent autonomously calls `assess_goal_quality` after identifying skill gaps

**`modules/skill_gap/prompts/skill_gap_identifier.py`**:
- Add `goal_assessment` to output format example
- Add directive 9: After identifying all skill gaps, call the `assess_goal_quality` tool with the learning goal and the skill gaps you just identified. Include the result in `goal_assessment`.
  - If vague: provide suggestion to rewrite goal with specifics
  - If all mastered: suggest a more advanced goal or adjacent topic

## 6. Self-correcting orchestrator with auto-refinement

**`modules/skill_gap/agents/skill_gap_identifier.py`** (`identify_skill_gap_with_llm()`):

```python
def identify_skill_gap_with_llm(llm, learning_goal, learner_information,
                                 skill_requirements=None, search_rag_manager=None):
    original_goal = learning_goal
    for attempt in range(2):  # max 1 refinement retry
        # Step 1: Map goal to skills (with retrieval)
        if not skill_requirements:
            mapper = SkillRequirementMapper(llm, search_rag_manager=search_rag_manager)
            effective_requirements = mapper.map_goal_to_skill({"learning_goal": learning_goal})
        else:
            effective_requirements = skill_requirements

        # Step 2: Identify gaps + assess goal (with assessment tool)
        identifier = SkillGapIdentifier(llm, search_rag_manager=search_rag_manager)
        skill_gaps = identifier.identify_skill_gap({
            "learning_goal": learning_goal,
            "learner_information": learner_information,
            "skill_requirements": effective_requirements,
        })

        # Step 3: Auto-refine if vague (only on first attempt)
        goal_assessment = skill_gaps.get("goal_assessment", {})
        if goal_assessment.get("is_vague") and attempt == 0:
            refiner = LearningGoalRefiner(llm)
            refined = refiner.refine_goal({
                "learning_goal": learning_goal,
                "learner_information": learner_information,
            })
            learning_goal = refined["refined_goal"]
            skill_requirements = None  # re-map with refined goal
            continue  # retry with refined goal

        break  # goal is good enough, or we already refined once

    # Annotate if auto-refined
    if learning_goal != original_goal:
        if "goal_assessment" not in skill_gaps:
            skill_gaps["goal_assessment"] = {}
        skill_gaps["goal_assessment"]["auto_refined"] = True
        skill_gaps["goal_assessment"]["original_goal"] = original_goal

    return skill_gaps, effective_requirements
```

Key design:
- **Max 1 auto-refinement** — if still vague after refinement, return as-is with `is_vague=true`
- **`auto_refined`** and **`original_goal`** added to response so frontend knows what happened
- **All-mastered** is never auto-refined — user must decide to change their goal

## 7. Wire through main.py

**`main.py` (~line 496)**:
- Pass existing module-level `search_rag_manager` (line 37) to `identify_skill_gap_with_llm()`
- Response now includes `goal_assessment` with auto-refinement info

---

## Latency Guardrails

### Agent-level limits
- **SkillRequirementMapper**: System prompt instructs max **3 tool calls** (1 syllabus query + 1-2 targeted queries). Prompt: "Make at most 3 retrieval calls. If results are insufficient after 3 calls, proceed with available information."
- **SkillGapIdentifier**: System prompt instructs max **1 tool call** (assess_goal_quality). The assessment is deterministic/fast.
- **Goal refinement**: Uses the existing `LearningGoalRefiner` — single LLM call (no tools, no iteration).

### Orchestrator-level limits
- **Max 1 auto-refinement** per request — the `for attempt in range(2)` loop
- **No cascading retries** — if refined goal is still vague, return with `is_vague=true` and let frontend handle it

### Estimated latency
- **Best case** (clear goal, content found): 2 LLM calls + 3-4 tool calls = ~5-8s
- **Vague goal, auto-refined**: 4 LLM calls + 4-5 tool calls = ~12-18s
- **No verified content**: 2 LLM calls + 1-2 empty retrieval calls = ~5-8s

---

## Tests

### New: `backend/tests/test_skill_gap_tools.py`

**`TestCourseContentRetrievalTool`** (6 tests):
- Returns formatted docs for valid query
- Filters by `content_category` (syllabus only, lectures only)
- Filters by `lecture_number`
- Returns "No results found" for unmatched query
- Returns "No verified content available" when `VerifiedContentManager` is None
- Combined category + lecture_number filtering

**`TestGoalAssessmentTool`** (7 tests):
- Returns `is_vague=true` when retrieval returns no results
- Returns `is_vague=false` when retrieval returns relevant results
- Returns `all_mastered=true` when all `is_gap=false`
- Returns `all_mastered=false` when at least one gap exists
- Returns appropriate suggestion text for vague goals
- Returns appropriate suggestion text for all-mastered
- Works when `skill_gaps=None` (only checks vagueness)

**`TestGoalRefinementTool`** (4 tests):
- Returns refined goal with `was_refined=true`
- Preserves original intent
- Works with empty learner_information
- Works with empty course_context

### New: `backend/tests/test_skill_gap_schemas.py`

**`TestGoalAssessmentSchema`** (4 tests):
- Valid GoalAssessment passes validation
- Default values work correctly
- SkillGaps with goal_assessment validates
- SkillGaps without goal_assessment uses default (backward compat)

### New: `backend/tests/test_skill_gap_orchestrator.py`

**`TestAutoRefinementLoop`** (5 tests):
- Vague goal triggers auto-refinement, retries with refined goal
- Non-vague goal does not trigger refinement
- All-mastered goal does not trigger refinement
- Max 1 refinement (doesn't loop forever)
- Auto-refinement info (`auto_refined`, `original_goal`) included in response

### Update: `backend/tests/test_onboarding_api.py`

- Update `MOCK_SKILL_GAPS_RESULT` to include `goal_assessment` field
- Add test: response includes `goal_assessment` with expected fields
- Verify `identify_skill_gap_with_llm` is called with `search_rag_manager` kwarg

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `modules/skill_gap/tools/__init__.py` | NEW | Package init |
| `modules/skill_gap/tools/course_content_retrieval_tool.py` | NEW | Retrieval tool |
| `modules/skill_gap/tools/goal_assessment_tool.py` | NEW | Goal assessment tool |
| `modules/skill_gap/tools/goal_refinement_tool.py` | NEW | Goal refinement tool |
| `modules/skill_gap/agents/skill_requirement_mapper.py` | MODIFY | Tool-calling agent |
| `modules/skill_gap/prompts/skill_requirement_mapper.py` | MODIFY | Retrieval tool instructions |
| `modules/skill_gap/schemas.py` | MODIFY | Add GoalAssessment model |
| `modules/skill_gap/agents/skill_gap_identifier.py` | MODIFY | Tool-calling agent + orchestrator |
| `modules/skill_gap/prompts/skill_gap_identifier.py` | MODIFY | Goal assessment tool usage |
| `main.py` | MODIFY | Wire search_rag_manager |
| `tests/test_skill_gap_tools.py` | NEW | Tool tests (17 tests) |
| `tests/test_skill_gap_schemas.py` | NEW | Schema tests (4 tests) |
| `tests/test_skill_gap_orchestrator.py` | NEW | Orchestrator tests (5 tests) |
| `tests/test_onboarding_api.py` | MODIFY | Add goal_assessment tests |

## Key Existing Code to Reuse
- `SearchRagManager` / `VerifiedContentManager` — `base/search_rag.py`, `base/verified_content_manager.py`
- `format_docs()` — `base/search_rag.py`
- `LearningGoalRefiner` — `modules/skill_gap/agents/learning_goal_refiner.py` (wrap in tool)
- Document metadata: `content_category`, `lecture_number` — from `base/verified_content_loader.py`
- `search_rag_manager` module-level in `main.py` (line 37)
- Factory tool pattern — `modules/learning_plan_generator/tools/learner_simulation_tool(1).py`
- Test patterns — `tests/test_onboarding_api.py` (mocking, TestClient, isolated fixtures)

## Verification
1. `python -m pytest backend/tests/test_skill_gap_tools.py backend/tests/test_skill_gap_schemas.py backend/tests/test_skill_gap_orchestrator.py -v`
2. `python -m pytest backend/tests/test_onboarding_api.py -v`
3. Start server with verified content indexed
4. `POST /identify-skill-gap-with-info` with course goal → skills grounded in syllabus (check logs for tool calls)
5. Specific goal ("lecture 3 of course X") → skills reflect lecture content
6. Vague goal ("learn stuff") → auto-refined, `goal_assessment.auto_refined == true`
7. Still-vague after refinement → `is_vague == true`
8. Expert learner → `all_mastered == true`
9. `python -m pytest backend/tests/ -v` — all tests pass
