# LLM Quality Gate, Third-Person Feedback, FSLSM Prompt Reinforcement, learner_simulator Removal

## Context

Four interrelated changes motivated by the same underlying problem: logic that belonged to the LLM was being second-guessed by deterministic post-processing, and module boundaries were blurred by a `learner_simulator` module that mixed path-evaluation and content-evaluation concerns.

### 1. Quality Gate

The deterministic keyword-scanning gate in `learning_plan_pipeline.py` checked the simulation feedback for strings like `"needs improvement"` or `"lacking"`. This approach missed nuanced negative signals (e.g., `"needs foundational support"`) and produced no actionable guidance for the reflexion step — only a pass/fail boolean with a list of matched keywords.

Extending the simulator output with `is_acceptable` + `improvement_directives` gives a single LLM call that handles both evaluation and improvement guidance, consistent with the pattern used in the skill gap pipeline.

### 2. Third-Person Feedback

The simulator was framed as role-playing the learner (first-person: "my preferences", "I thrive"). The frontend displays the output as an objective assessment. The framing was changed to third-person throughout: "The learner would likely find...", "This learner may struggle with...".

### 3. FSLSM Overrides

`utils/fslsm.py._apply_fslsm_overrides()` post-processed LLM output with hard binary thresholds (|value| >= 0.7). This treated the LLM as untrustworthy for intermediate dimension values and silently overrode its decisions. The same rules were already in the scheduler prompt but expressed as binary on/off switches. The override was removed and the prompt was strengthened with proportional, nuanced guidance (e.g., "strong negative < -0.7 → multiple checkpoints; mild negative -0.3 to -0.7 → one checkpoint").

### 4. learner_simulator Removal

The module mixed path-evaluation concerns (belong in `learning_plan_generator`) and content-evaluation concerns (belong in `content_generator`). Three files imported from it:

| Consumer | Import | New source |
|---|---|---|
| `main.py` | `simulate_content_feedback_with_llm` | `content_generator.agents.content_feedback_simulator` |
| `plan_feedback_simulator.py` | `LearnerFeedback` schema | `LearnerPlanFeedback` (new, in `learning_plan_generator.schemas`) |
| `learner_simulation_tool.py` | `create_ground_truth_profile_with_llm` | `learning_plan_generator.agents.ground_truth_profile_creator` |

---

## Architecture

### Updated Data Flow

```
schedule_session()  [main LLM — no FSLSM post-processing]
    ↓
sim_tool.invoke()  [gpt-4o-mini — LearningPlanFeedbackSimulator]
    → simulation_feedback: {
          feedback (3rd person),
          suggestions,
          is_acceptable,
          issues,               ← short phrases for frontend bullet points
          improvement_directives  ← full actionable text for reflexion
      }
    ↓
Read is_acceptable, issues, improvement_directives directly
    ↓
if not is_acceptable and iterations remain:
    scheduler.reflexion({
        ...,
        "evaluator_feedback": improvement_directives
    })
    ↑ Injected into prompt as {evaluator_feedback}
      → scheduler addresses specific issues
```

### Module Structure After Change

```
modules/
├── learning_plan_generator/
│   ├── agents/
│   │   ├── ground_truth_profile_creator.py   ← moved from learner_simulator/
│   │   ├── learning_path_scheduler.py
│   │   └── plan_feedback_simulator.py
│   ├── prompts/
│   │   ├── ground_truth_profile.py           ← moved from learner_simulator/
│   │   ├── learning_path_scheduling.py       ← updated FSLSM guidance
│   │   └── plan_feedback.py                  ← third-person + quality gate
│   ├── orchestrators/
│   │   └── learning_plan_pipeline.py         ← removed keyword gate
│   └── schemas.py                            ← LearnerPlanFeedback, GroundTruthProfileResult
├── content_generator/
│   ├── agents/
│   │   └── content_feedback_simulator.py     ← moved from learner_simulator/
│   ├── prompts/
│   │   └── content_feedback_simulator.py     ← moved from learner_simulator/
│   └── schemas.py                            ← FeedbackDetail, LearnerFeedback
└── learner_simulator/                        ← DELETED
```

---

## Changes

### Part 1 — Quality Gate + Third-Person Feedback

**`learning_plan_generator/schemas.py`**
- Added `PlanFeedbackDimensions`, `LearnerPlanFeedback` (with `is_acceptable: bool`, `issues: List[str]`, `improvement_directives: str`)
- Added `GroundTruthProfileResult` and `parse_ground_truth_profile_result()` (moved from `learner_simulator/schemas.py` in Part 2)

**`learning_plan_generator/prompts/plan_feedback.py`**
- Renamed agent from "Learner Feedback Simulator" to "Plan Quality Assessor"
- Removed role-play framing ("you are role-playing a specific learner")
- System prompt now instructs third-person perspective throughout
- Added explicit quality gate rules: when to set `is_acceptable: false`, when to populate `issues` and `improvement_directives`
- Extended output format with `is_acceptable`, `issues`, `improvement_directives`

**`learning_plan_generator/agents/plan_feedback_simulator.py`**
- Replaced `from modules.learner_simulator.schemas import LearnerFeedback` with `from modules.learning_plan_generator.schemas import LearnerPlanFeedback`
- `feedback_path()` validates against `LearnerPlanFeedback` instead of `LearnerFeedback`

**`learning_plan_generator/prompts/learning_path_scheduling.py`**
- Added `{evaluator_feedback}` section to `learning_path_scheduler_task_prompt_reflexion`
- Updated Task B directive to treat `evaluator_feedback` as highest-priority when non-empty
- **Replaced binary FSLSM rules** (if <= -0.7 then X) with **proportional magnitude guidance** across five bands: strong negative, mild negative, near-zero, mild positive, strong positive — for all four dimensions
- Added mastery threshold mapping table (beginner → 60, intermediate → 70, advanced → 80, expert → 90)

**`learning_plan_generator/agents/learning_path_scheduler.py`**
- Removed `from modules.learning_plan_generator.utils.fslsm import _parse_profile, _apply_fslsm_overrides`
- Added `evaluator_feedback: str = Field(default="")` to `LearningPathRefinementPayload`
- Removed FSLSM override calls in `schedule_session()`, `reflexion()`, and `reschedule()`

**`learning_plan_generator/orchestrators/learning_plan_pipeline.py`**
- Removed `_NEGATIVE_KEYWORDS` list and `_evaluate_plan_quality()` function
- Added `import logging`
- Pipeline now reads quality directly from simulation feedback:
  ```python
  if not isinstance(simulation_feedback, dict):
      simulation_feedback = {}
  quality = {
      "pass": simulation_feedback.get("is_acceptable", True),
      "issues": simulation_feedback.get("issues", []),
      "feedback_summary": simulation_feedback.get("feedback", {}),
  }
  evaluator_feedback = simulation_feedback.get("improvement_directives", "")
  ```
- Passes `evaluator_feedback` to `reflexion()` on subsequent iterations

**`learning_plan_generator/orchestrators/__init__.py`**
- Removed `_evaluate_plan_quality` from exports

**`main.py`**
- Removed `_evaluate_plan_quality` from import
- Replaced inline call with direct dict extraction (same `is_acceptable`/`issues`/`feedback_summary` pattern)

**`tests/test_plan_quality_gate.py`** — full rewrite
- `test_is_acceptable_true_breaks_loop_after_first_attempt`
- `test_is_acceptable_false_triggers_reflexion`
- `test_improvement_directives_passed_to_reflexion`
- `test_non_dict_simulation_feedback_defaults_to_pass`
- `test_issues_extracted_from_simulation_feedback`
- `test_feedback_summary_extracted_from_simulation_feedback`

**`tests/test_agentic_learning_plan.py`** — updated
- Removed `_evaluate_plan_quality` import; replaced stale `TestAgenticMetadata` tests with LLM-gate equivalents

**`tests/test_goal_context_plumbing.py`** — updated
- Removed `patch(..._evaluate_plan_quality)` from `test_schedule_learning_path_agentic_accepts_goal_context`; sim tool now returns full `LearnerPlanFeedback`-shaped dict

---

### Part 2 — learner_simulator Module Removal

**Created `learning_plan_generator/agents/ground_truth_profile_creator.py`**
- Moved `GroundTruthProfileCreator`, `GroundTruthProfileCreatePayload`, `GroundTruthProfileProgressPayload`, `create_ground_truth_profile_with_llm()`
- Updated imports to `learning_plan_generator.schemas` and `learning_plan_generator.prompts.ground_truth_profile`

**Created `learning_plan_generator/prompts/ground_truth_profile.py`**
- Moved `ground_truth_profile_creator_system_prompt`, `ground_truth_profile_creator_task_prompt`, `ground_truth_profile_creator_task_prompt_progress`

**Created `content_generator/agents/content_feedback_simulator.py`**
- Moved `LearningContentFeedbackSimulator`, `LearningContentFeedbackPayload`, `simulate_content_feedback_with_llm()`
- Updated imports to `content_generator.schemas` and `content_generator.prompts.content_feedback_simulator`

**Created `content_generator/prompts/content_feedback_simulator.py`**
- Moved `learner_feedback_simulator_system_prompt`, `learner_feedback_simulator_task_prompt_content`
- Deleted `learner_feedback_simulator_task_prompt_path` (unused — learning_plan_generator has its own path feedback prompt)

**Updated `content_generator/schemas.py`**
- Appended `FeedbackDetail` and `LearnerFeedback` schemas

**Updated `modules/tools/learner_simulation_tool.py`**
- Changed `from modules.learner_simulator import create_ground_truth_profile_with_llm` → `from modules.learning_plan_generator.agents.ground_truth_profile_creator import create_ground_truth_profile_with_llm`

**Updated `main.py`**
- Changed `from modules.learner_simulator import simulate_content_feedback_with_llm` → `from modules.content_generator.agents.content_feedback_simulator import simulate_content_feedback_with_llm`

**Updated `learning_plan_generator/agents/__init__.py`**
- Added exports for `GroundTruthProfileCreator`, `create_ground_truth_profile_with_llm`

**Updated `content_generator/agents/__init__.py`**
- Added exports for `LearningContentFeedbackSimulator`, `simulate_content_feedback_with_llm`

**Deleted `modules/learner_simulator/`** — entire directory removed
- `LearningPlanFeedbackSimulator` in `learner_feedback_simulators.py` — superseded by `learning_plan_generator/agents/plan_feedback_simulator.py`
- `LearnerInteractionSimulator` + `LearnerBehaviorLog` in `learner_behavior_simulator.py` — not on the main application path; removed outright
- `GroundTruthProfileCreator` in `grounding_profile_creator.py` — moved to `learning_plan_generator`
- `LearningContentFeedbackSimulator` in `learner_feedback_simulators.py` — moved to `content_generator`

---

### Part 3 — FSLSM Override Removal

**Deleted `learning_plan_generator/utils/fslsm.py`**
- `_parse_profile()` — no callers after removing override calls from scheduler
- `_apply_fslsm_overrides()` — replaced by proportional LLM prompt guidance

**Deleted `learning_plan_generator/utils/`** — entire directory removed (was only ever used for `fslsm.py`)

**Updated `tests/test_fslsm_overrides.py`** — replaced with placeholder
- Original tests verified deterministic behaviour of the deleted function
- FSLSM alignment is now verified end-to-end by `LearnerPlanFeedbackSimulator` (which sets `is_acceptable: false` when FSLSM structural fields are misaligned)

---

## Design Decisions

**Why not keep `_evaluate_plan_quality` as a fallback?**
The function's keyword list required constant maintenance to catch new phrasings. Any phrase the list missed would silently pass as acceptable. The LLM assessor understands context, so "needs foundational support" is correctly flagged without adding the phrase to a list. The only risk is LLM cost, which is mitigated by using `gpt-4o-mini` for the simulation pass.

**Why third-person for the plan assessor?**
The frontend displays simulation output as an objective quality report. First-person phrasing ("I find this confusing") reads oddly in that context and can mislead users about the nature of the assessment.

**Why keep the `issues` list separate from `improvement_directives`?**
`issues` is short-phrase content for frontend bullet points (1–3 items, e.g., "Pacing too fast for beginner level"). `improvement_directives` is the full actionable text the scheduler needs to address them. Mixing the two into a single field would force the frontend to parse the directive text for display.

**Why proportional FSLSM guidance instead of binary thresholds?**
A learner with `fslsm_processing = -0.5` (moderately active) was getting no checkpoint challenges at all under the binary rule (threshold was -0.7). Proportional guidance acknowledges that mild preferences warrant mild adaptations. The LLM is also better positioned than a threshold to combine multiple dimension signals into a coherent session structure.

**Why move `ground_truth_profile_creator` to `learning_plan_generator` rather than creating a shared `base` utility?**
Ground truth profile creation is used exclusively for evaluating learning path quality (it enriches the simulator profile). It has no role in content generation or other modules. Co-locating it with the learning plan generator keeps the dependency graph simple.
