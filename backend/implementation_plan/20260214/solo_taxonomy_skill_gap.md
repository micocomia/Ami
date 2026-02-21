# SOLO Taxonomy: Skill Gap Agent Changes

## Context

The learner_profiler agent has been updated to support 5 SOLO taxonomy levels (`unlearned`, `beginner`, `intermediate`, `advanced`, `expert`). The skill_gap module must match, otherwise:
- Pydantic validation will reject `expert` values coming from the profiler
- The `check_gap_consistency` validator will crash on unknown levels
- LLM prompts won't know `expert` is a valid option

---

## Files to Modify

### 1. `backend/modules/skill_gap/schemas.py`

**a) Update `LevelRequired` enum** (lines 7-10) — add `expert`:
```python
class LevelRequired(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"
```

**b) Update `LevelCurrent` enum** (lines 13-17) — add `expert`:
```python
class LevelCurrent(str, Enum):
    unlearned = "unlearned"
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"
```

**c) Update `check_gap_consistency` validator** (lines 73-74) — add `expert` to ordering dict:
```python
order = {"unlearned": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
```

### 2. `backend/modules/skill_gap/prompts/skill_gap_identifier.py`

**a) Update system prompt directive 6** — add `expert` to allowed `current_level` values:

Change:
```
* `current_level` must be one of: "unlearned", "beginner", "intermediate", "advanced".
```
To:
```
* `current_level` must be one of: "unlearned", "beginner", "intermediate", "advanced", "expert".
```

**b) Add SOLO taxonomy guidance** to the system prompt, similar to what was added in the learner profiler. Add after directive 6:
```
8.  **Use SOLO Reasoning**: Proficiency levels map to the SOLO taxonomy — assess the *quality* of understanding:
    * `unlearned` (Prestructural): No relevant understanding of the skill.
    * `beginner` (Unistructural): Grasps one relevant aspect in isolation.
    * `intermediate` (Multistructural): Knows multiple aspects but hasn't integrated them.
    * `advanced` (Relational): Integrates concepts into a coherent whole.
    * `expert` (Extended Abstract): Can generalize and transfer knowledge to new contexts.
```

**c) Update output format example** — consider adding an `expert` example or at least noting all valid levels in a comment.

### 3. `backend/modules/skill_gap/prompts/skill_requirement_mapper.py`

**a) Update system prompt directive 4**:

Change:
```
4.  **Adhere to Levels**: The `required_level` must be one of: "beginner", "intermediate", or "advanced".
```
To:
```
4.  **Adhere to Levels**: The `required_level` must be one of: "beginner", "intermediate", "advanced", or "expert".
```

**b) Update output format**:

Change:
```
"required_level": "beginner|intermediate|advanced"
```
To:
```
"required_level": "beginner|intermediate|advanced|expert"
```

(In both example entries.)

---

## Verification

1. **Enum check**: `python -c "from modules.skill_gap.schemas import LevelRequired, LevelCurrent; print(list(LevelRequired)); print(list(LevelCurrent))"` from `backend/` — should show 5 levels each
2. **Ordering check**: `python -c "from modules.skill_gap.schemas import SkillGap; SkillGap(name='test', is_gap=True, required_level='expert', current_level='advanced', reason='test reason', level_confidence='medium')"` — should validate successfully (advanced < expert → is_gap=True)
3. **Existing tests**: `python -m pytest backend/tests/ -v` — all should pass
