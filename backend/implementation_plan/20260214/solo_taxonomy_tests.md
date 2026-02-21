# SOLO Taxonomy: Test Updates & New Tests

## Context

After adding `expert` across all modules, existing tests need updating and new tests should be added to cover the 5th level.

---

## Existing Tests to Update

### 1. `backend/tests/test_onboarding_api.py` — line 518

**Update config endpoint assertion:**

Change:
```python
def test_get_config_skill_levels_contains_expected_values(self, client):
    levels = client.get("/config").json()["skill_levels"]
    assert levels == ["unlearned", "beginner", "intermediate", "advanced"]
```
To:
```python
def test_get_config_skill_levels_contains_expected_values(self, client):
    levels = client.get("/config").json()["skill_levels"]
    assert levels == ["unlearned", "beginner", "intermediate", "advanced", "expert"]
```

### 2. Existing fixtures — NO changes needed

These fixtures use valid levels that remain valid after the change:
- `test_onboarding_api.py` lines 78-113: mock data uses `"beginner"`, `"intermediate"`, `"advanced"` — all still valid
- `test_fslsm_update.py` lines 24-30: uses `"advanced"`, `"intermediate"`, `"unlearned"` — all still valid
- `test_store_and_auth.py` line 51: uses `"beginner"` — still valid

---

## New Tests to Add

### 1. New file: `backend/tests/test_solo_taxonomy.py`

This file tests SOLO taxonomy enum coverage and validation across all modules.

```python
"""Tests for SOLO taxonomy (5-level proficiency) across all modules."""

import pytest


class TestLearnerProfilerEnums:
    """Verify learner_profiler enums include all 5 SOLO levels."""

    def test_current_level_has_five_values(self):
        from modules.learner_profiler.schemas import CurrentLevel
        assert len(CurrentLevel) == 5
        assert set(CurrentLevel.__members__) == {
            "unlearned", "beginner", "intermediate", "advanced", "expert"
        }

    def test_required_level_has_four_values(self):
        from modules.learner_profiler.schemas import RequiredLevel
        assert len(RequiredLevel) == 4
        assert set(RequiredLevel.__members__) == {
            "beginner", "intermediate", "advanced", "expert"
        }

    def test_current_level_accepts_expert(self):
        from modules.learner_profiler.schemas import CurrentLevel
        assert CurrentLevel("expert") == CurrentLevel.expert

    def test_required_level_accepts_expert(self):
        from modules.learner_profiler.schemas import RequiredLevel
        assert RequiredLevel("expert") == RequiredLevel.expert

    def test_in_progress_skill_with_expert(self):
        from modules.learner_profiler.schemas import InProgressSkill
        skill = InProgressSkill(
            name="Test Skill",
            required_proficiency_level="expert",
            current_proficiency_level="advanced",
        )
        assert skill.required_proficiency_level.value == "expert"
        assert skill.current_proficiency_level.value == "advanced"

    def test_mastered_skill_with_expert(self):
        from modules.learner_profiler.schemas import MasteredSkill
        skill = MasteredSkill(name="Test Skill", proficiency_level="expert")
        assert skill.proficiency_level.value == "expert"


class TestSkillGapEnums:
    """Verify skill_gap enums include all 5 SOLO levels."""

    def test_level_current_has_five_values(self):
        from modules.skill_gap.schemas import LevelCurrent
        assert len(LevelCurrent) == 5
        assert set(LevelCurrent.__members__) == {
            "unlearned", "beginner", "intermediate", "advanced", "expert"
        }

    def test_level_required_has_four_values(self):
        from modules.skill_gap.schemas import LevelRequired
        assert len(LevelRequired) == 4
        assert set(LevelRequired.__members__) == {
            "beginner", "intermediate", "advanced", "expert"
        }

    def test_skill_gap_expert_is_gap(self):
        """current=advanced, required=expert → is_gap=True"""
        from modules.skill_gap.schemas import SkillGap
        gap = SkillGap(
            name="Test",
            is_gap=True,
            required_level="expert",
            current_level="advanced",
            reason="Needs transfer skills",
            level_confidence="medium",
        )
        assert gap.is_gap is True

    def test_skill_gap_expert_not_gap(self):
        """current=expert, required=expert → is_gap=False"""
        from modules.skill_gap.schemas import SkillGap
        gap = SkillGap(
            name="Test",
            is_gap=False,
            required_level="expert",
            current_level="expert",
            reason="Fully proficient",
            level_confidence="high",
        )
        assert gap.is_gap is False

    def test_skill_gap_expert_exceeds_required(self):
        """current=expert, required=advanced → is_gap=False"""
        from modules.skill_gap.schemas import SkillGap
        gap = SkillGap(
            name="Test",
            is_gap=False,
            required_level="advanced",
            current_level="expert",
            reason="Exceeds requirement",
            level_confidence="high",
        )
        assert gap.is_gap is False

    def test_skill_gap_inconsistent_expert_raises(self):
        """current=advanced, required=expert but is_gap=False → should raise"""
        from modules.skill_gap.schemas import SkillGap
        with pytest.raises(ValueError, match="is_gap inconsistency"):
            SkillGap(
                name="Test",
                is_gap=False,
                required_level="expert",
                current_level="advanced",
                reason="Inconsistent",
                level_confidence="medium",
            )

    def test_skill_requirement_accepts_expert(self):
        from modules.skill_gap.schemas import SkillRequirement
        req = SkillRequirement(name="Test", required_level="expert")
        assert req.required_level.value == "expert"


class TestLearningPlanGeneratorEnums:
    """Verify learning_plan_generator enum includes expert."""

    def test_proficiency_has_four_values(self):
        from modules.learning_plan_generator.schemas import Proficiency
        assert len(Proficiency) == 4
        assert set(Proficiency.__members__) == {
            "beginner", "intermediate", "advanced", "expert"
        }

    def test_desired_outcome_accepts_expert(self):
        from modules.learning_plan_generator.schemas import DesiredOutcome
        outcome = DesiredOutcome(name="Test Skill", level="expert")
        assert outcome.level.value == "expert"
```

**Run command:**
```bash
cd backend && python -m pytest tests/test_solo_taxonomy.py -v
```

**Note:** These tests import directly from module schemas, which should work without the full langchain dependency stack as long as you run from `backend/` with `sys.path` including the current directory. If imports fail due to `modules/__init__.py` pulling in langchain-dependent agents, you may need to either:
- Run with the full dependency stack, or
- Temporarily guard the imports in `modules/__init__.py`

---

## Verification

After implementing all SOLO taxonomy changes across all modules:

```bash
# Run the new SOLO taxonomy tests
cd backend && python -m pytest tests/test_solo_taxonomy.py -v

# Run the updated config test
cd backend && python -m pytest tests/test_onboarding_api.py::TestConfigEndpoint -v

# Run all existing tests to check for regressions
cd backend && python -m pytest tests/ -v
```
