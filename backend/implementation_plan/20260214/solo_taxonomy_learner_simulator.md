# SOLO Taxonomy: Learner Simulator Agent Changes

## Context

The learner_simulator generates synthetic learner profiles and behavior logs for testing. Its prompts reference proficiency levels in output format examples. These must be updated to include `expert` and ideally use SOLO reasoning so simulated profiles are realistic.

No schema changes are needed — the simulator uses `Dict[str, Any]` for profiles, not typed enums.

---

## Files to Modify

### 1. `backend/modules/learner_simulator/prompts.py`

**a) Update `ground_truth_profile_creator_system_prompt`** — add SOLO taxonomy context to the Cognitive Status section:

Current text:
```
- **Cognitive Status**: Mastered skills, in-progress skills, and knowledge gaps relevant to the learner's goals.
```

Change to:
```
- **Cognitive Status**: Mastered skills, in-progress skills, and knowledge gaps relevant to the learner's goals. Proficiency levels follow the SOLO taxonomy:
  * `unlearned` (Prestructural): No relevant understanding.
  * `beginner` (Unistructural): Grasps one relevant aspect in isolation.
  * `intermediate` (Multistructural): Knows multiple aspects but hasn't integrated them.
  * `advanced` (Relational): Integrates concepts into a coherent whole.
  * `expert` (Extended Abstract): Can generalize and transfer knowledge to new contexts.
```

**b) Update `ground_truth_profile_creator_task_prompt_progress`** output format — the mastered_skills example currently shows:
```json
"proficiency_level": "advanced (final actual proficiency level)"
```

Change to:
```json
"proficiency_level": "advanced (one of: beginner, intermediate, advanced, expert)"
```

**c) Update `ground_truth_profile_creator_task_prompt_progress`** Cognitive Status Update section — the instruction text says:
```
Reflect the final proficiency level (e.g., from intermediate to advanced)
```

Change to:
```
Reflect the final proficiency level (e.g., from intermediate to advanced, or from advanced to expert). Proficiency transitions represent qualitative shifts: intermediate → advanced means concepts are now integrated; advanced → expert means knowledge can be generalized to new contexts.
```

---

## Verification

1. **Import check**: `python -c "from modules.learner_simulator.prompts import ground_truth_profile_creator_system_prompt; print('OK')"` from `backend/`
2. **Grep check**: `grep -n "expert" backend/modules/learner_simulator/prompts.py` — should show the new references
3. **Existing tests**: `python -m pytest backend/tests/ -v`
