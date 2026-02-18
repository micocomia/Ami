# SOLO Taxonomy: Learning Plan Generator Agent Changes

## Context

The learner_profiler now supports `expert` as a 5th proficiency level. The learning_plan_generator's `Proficiency` enum and prompts must match, otherwise `DesiredOutcome` objects with `level="expert"` will fail Pydantic validation.

---

## Files to Modify

### 1. `backend/modules/learning_plan_generator/schemas.py`

**Update `Proficiency` enum** (lines 9-12) — add `expert`:
```python
class Proficiency(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"
```

### 2. `backend/modules/learning_plan_generator/prompts/learning_path_scheduling.py`

**Update output format example** — the current example only shows `"intermediate"` and `"advanced"` as sample levels. Update the example to mention `expert` is valid. Suggested change to the `desired_outcome_when_completed` example:

```json
"desired_outcome_when_completed": [
    {"name": "Skill 1", "level": "intermediate"},
    {"name": "Skill 2", "level": "advanced"}
]
```

Change to:
```json
"desired_outcome_when_completed": [
    {"name": "Skill 1", "level": "intermediate"},
    {"name": "Skill 2", "level": "expert"}
]
```

Or add a comment noting valid levels are `beginner`, `intermediate`, `advanced`, `expert`.

**Optionally add SOLO context** to the system prompt. This is lower priority since the learning path scheduler doesn't directly assess proficiency — it consumes levels from the profiler. But it would help the LLM generate appropriate session difficulty progressions. Could add a brief note in the Universal Core Directives:
```
6.  **Proficiency Levels**: Valid levels are "beginner", "intermediate", "advanced", "expert" (SOLO taxonomy). Sessions should progressively build toward the target level.
```

---

## Verification

1. **Enum check**: `python -c "from modules.learning_plan_generator.schemas import Proficiency; print(list(Proficiency))"` from `backend/`
2. **Validation check**: `python -c "from modules.learning_plan_generator.schemas import DesiredOutcome; print(DesiredOutcome(name='test', level='expert'))"` — should succeed
3. **Existing tests**: `python -m pytest backend/tests/ -v`
