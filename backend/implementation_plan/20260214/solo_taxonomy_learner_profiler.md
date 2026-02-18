# SOLO Taxonomy: Learner Profiler Agent Changes

## Context

The system currently uses a 4-tier linear proficiency taxonomy (`unlearned`, `beginner`, `intermediate`, `advanced`). We are expanding to 5 levels that map to the SOLO taxonomy while keeping user-friendly names:

| User-Facing Name | SOLO Level | Meaning |
|---|---|---|
| `unlearned` | Prestructural | No relevant understanding |
| `beginner` | Unistructural | One relevant aspect grasped |
| `intermediate` | Multistructural | Multiple aspects known, not yet integrated |
| `advanced` | Relational | Aspects integrated into a coherent whole |
| `expert` | Extended Abstract | Can generalize and transfer to new contexts |

The key change: **add `expert` as a 5th level** and update all prompts so the LLM reasons with SOLO-level semantics behind these familiar labels.

---

## Files Modified

### 1. `backend/modules/learner_profiler/schemas.py`

**Updated `RequiredLevel` enum** (lines 9-13) -- added `expert`:
```python
class RequiredLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"
```

**Updated `CurrentLevel` enum** (lines 16-21) -- added `expert`:
```python
class CurrentLevel(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"
```

### 2. `backend/modules/learner_profiler/prompts/adaptive_learning_profiler.py`

**a) Updated `learner_profile_output_format`** -- updated example comments to list all valid levels including `expert`, so the LLM knows the full set of allowed values for `proficiency_level`, `required_proficiency_level`, and `current_proficiency_level`.

**b) Updated `adaptive_learner_profiler_system_prompt_base`** -- added a SOLO taxonomy explanation to the Cognitive Status section. Explains what each level means in terms of *quality of understanding*:
- `unlearned` (Prestructural): No relevant understanding of the skill
- `beginner` (Unistructural): Grasps one relevant aspect in isolation
- `intermediate` (Multistructural): Knows multiple aspects but hasn't integrated them
- `advanced` (Relational): Integrates concepts into a coherent whole
- `expert` (Extended Abstract): Can generalize and transfer knowledge to new contexts

Instructs the agent to reason about the *nature* of understanding when assessing proficiency (e.g., "learner recalls multiple facts but cannot explain relationships between them -> intermediate").

**c) Updated `adaptive_learner_profiler_basic_system_prompt_task_chain_of_thoughts`**:
- Task A CoT step 3: added SOLO-level reasoning guidance when categorizing skills (determine whether the learner has no understanding, grasps a single aspect, knows multiple aspects without integration, integrates concepts coherently, or can generalize to new contexts)
- Task B CoT step 2: added guidance that proficiency transitions represent qualitative shifts (e.g., intermediate -> advanced means the learner now *integrates* concepts, not just accumulates them; advanced -> expert means the learner can now *generalize and transfer* knowledge)

**d) Updated `adaptive_learner_profiler_basic_system_prompt_requirements`**:
- Changed allowed values from `"unleared", "beginner", "intermediate", "advanced"` to `"unlearned", "beginner", "intermediate", "advanced", "expert"` (also fixes the typo "unleared")

**e) Updated `adaptive_learner_profiler_task_prompt_update`**:
- Added note after the example listing all valid levels: "unlearned", "beginner", "intermediate", "advanced", "expert"

### 3. Deleted `backend/modules/learner_profiler/prompts.py` (duplicate cleanup)

This file was an exact duplicate of `prompts/adaptive_learning_profiler.py`. The agent imports from the `prompts/` package (`from ..prompts import ...`), which resolves to `prompts/__init__.py` -> `prompts/adaptive_learning_profiler.py`. The root-level `prompts.py` was shadowed by the package and never imported.

---

## Out of Scope

These files also need SOLO updates but belong to other agents (separate tasks per the impact doc):
- `backend/modules/skill_gap/schemas.py` -- `LevelRequired`, `LevelCurrent` enums + gap validation ordering
- `backend/modules/skill_gap/prompts/`
- `backend/modules/learning_plan_generator/prompts/`
- `backend/modules/learner_simulator/prompts.py`

---

## Verification

1. **Enum check**: `python -c "from modules.learner_profiler.schemas import CurrentLevel, RequiredLevel; print(list(CurrentLevel)); print(list(RequiredLevel))"` from `backend/` -- should show 5 levels each
2. **Import check**: Verify the agent still imports correctly after deleting the duplicate `prompts.py`
3. **Existing tests**: `python -m pytest backend/tests/test_fslsm_update.py -v` -- should still pass (test fixture uses `"advanced"`, `"intermediate"`, `"unlearned"` which remain valid)
4. **Full test suite**: `python -m pytest backend/tests/ -v` -- check nothing else breaks
