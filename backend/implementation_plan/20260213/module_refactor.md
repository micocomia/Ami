# Module Refactor Plan

## Context

The `modules/personalized_resource_delivery/` module bundles learning path scheduling, content generation, and feedback simulation into one package. This refactor splits it into focused modules with clearer responsibilities. Additionally, existing modules are renamed for clarity.

## Final Module Structure

```
modules/
├── skill_gap/                          (renamed from skill_gap_identification)
├── learner_profiler/                   (renamed from adaptive_learner_modeling)
├── learner_simulator/                  (renamed from learner_simulation + feedback simulators added)
├── learning_plan_generator/            (NEW — scheduler + tool)
├── content_generator/                  (NEW — content pipeline)
└── ai_chatbot_tutor/                   (unchanged)
```

---

## Part A: Split `personalized_resource_delivery` into 3 modules

### A1. Create `modules/learning_plan_generator/`

```
learning_plan_generator/
├── __init__.py
├── schemas.py              # Proficiency, DesiredOutcome, SessionItem, LearningPath
├── agents/
│   ├── __init__.py
│   └── learning_path_scheduler.py
├── prompts/
│   ├── __init__.py
│   └── learning_path_scheduling.py
└── tools/
    ├── __init__.py
    └── learner_simulation_tool.py
```

- **schemas.py**: Move `Proficiency`, `DesiredOutcome`, `SessionItem`, `LearningPath` from `personalized_resource_delivery/schemas.py`
- **prompts/learning_path_scheduling.py**: Copy verbatim (pure strings, no imports)
- **agents/learning_path_scheduler.py**: Copy with updated imports → `from modules.learning_plan_generator.schemas` and `from modules.learning_plan_generator.prompts.learning_path_scheduling`
- **tools/learner_simulation_tool.py**: Copy with fixed imports:
  - `LearnerFeedbackSimulator` → `LearningPlanFeedbackSimulator` from `modules.learner_simulator`
  - Fix broken `create_ground_truth_from_learner_profile_with_llm` → `create_ground_truth_profile_with_llm`

### A2. Create `modules/content_generator/`

```
content_generator/
├── __init__.py
├── schemas.py              # KnowledgeType, KnowledgePoint(s), KnowledgeDraft,
│                           # DocumentStructure, quiz models, ContentOutline,
│                           # LearningContent, etc.
├── agents/
│   ├── __init__.py
│   ├── goal_oriented_knowledge_explorer.py
│   ├── search_enhanced_knowledge_drafter.py
│   ├── learning_document_integrator.py
│   ├── document_quiz_generator.py
│   └── learning_content_creator.py
└── prompts/
    ├── __init__.py
    ├── goal_oriented_knowledge_explorer.py
    ├── search_enhanced_knowledge_drafter.py
    ├── learning_document_integrator.py
    ├── document_quiz_generator.py
    └── learning_content_creator.py
```

- **schemas.py**: Move `KnowledgeType`, `KnowledgePoint`, `KnowledgePoints`, `KnowledgeDraft`, `DocumentStructure`, quiz models (`SingleChoiceQuestion`, `MultipleChoiceQuestion`, `TrueFalseQuestion`, `ShortAnswerQuestion`, `DocumentQuiz`), `ContentSection`, `ContentOutline`, `QuizPair`, `LearningContent`, and parse helpers
- **prompts/**: Copy all 5 prompt files verbatim (pure strings)
- **agents/**: Copy all 5 agent files, update imports from `modules.personalized_resource_delivery.*` → `modules.content_generator.*`

### A3. Rename `learner_simulation` → `learner_simulator` and add feedback simulators

Create `modules/learner_simulator/` with all existing files from `learner_simulation/` plus new feedback files:

```
learner_simulator/
├── __init__.py                        (UPDATE — add feedback exports)
├── schemas.py                         (UPDATE — add FeedbackDetail, LearnerFeedback)
├── prompts.py                         (UPDATE — append feedback simulation prompts)
├── learner_feedback_simulators.py     (NEW — two split classes)
├── grounding_profile_creator.py       (copied, internal imports use relative so no changes)
└── learner_behavior_simulator.py      (copied, internal imports use relative so no changes)
```

- **`learner_feedback_simulators.py`** (NEW): Split `LearnerFeedbackSimulator` into:
  - `LearningPlanFeedbackSimulator` — has `feedback_path()` method
  - `LearningContentFeedbackSimulator` — has `feedback_content()` method
  - `simulate_path_feedback_with_llm()` convenience function
  - `simulate_content_feedback_with_llm()` convenience function
- **`schemas.py`** (APPEND): Add `FeedbackDetail`, `LearnerFeedback`
- **`prompts.py`** (APPEND): Add all feedback simulation prompts (system prompt, path task prompt, content task prompt, output formats)
- **`__init__.py`** (UPDATE): Export the new classes and functions
- All external references change from `modules.learner_simulation` → `modules.learner_simulator`
- Delete old `modules/learner_simulation/` directory

### A4. Update `main.py` imports

Replace:
```python
from modules.personalized_resource_delivery import *
from modules.personalized_resource_delivery.agents.learning_path_scheduler import refine_learning_path_with_llm
```

With:
```python
from modules.learning_plan_generator import *
from modules.learning_plan_generator.agents.learning_path_scheduler import refine_learning_path_with_llm
from modules.content_generator import *
from modules.learner_simulator import simulate_path_feedback_with_llm, simulate_content_feedback_with_llm
```

No route handler changes needed — all function names stay the same.

### A5. Delete `modules/personalized_resource_delivery/`

---

## Part B: Rename `skill_gap_identification` → `skill_gap`

### B1. Create `modules/skill_gap/`

```
skill_gap/
├── __init__.py
├── schemas.py
├── agents/
│   ├── __init__.py
│   ├── learning_goal_refiner.py
│   ├── skill_gap_identifier.py
│   └── skill_requirement_mapper.py
└── prompts/
    ├── __init__.py
    ├── learning_goal_refiner.py
    ├── skill_gap_identifier.py
    └── skill_requirement_mapper.py
```

- Copy all files, update internal imports from `modules.skill_gap_identification.*` → `modules.skill_gap.*` (relative imports stay relative)

### B2. Update references

- **`main.py`**: `from modules.skill_gap_identification import *` → `from modules.skill_gap import *`
- **`modules/__init__.py`**: Update the import line referencing `skill_gap_identification`

### B3. Delete `modules/skill_gap_identification/`

---

## Part C: Rename `adaptive_learner_modeling` → `learner_profiler`

### C1. Create `modules/learner_profiler/`

```
learner_profiler/
├── __init__.py
├── schemas.py
├── prompts.py                          (legacy file)
├── agents/
│   ├── __init__.py
│   └── adaptive_learning_profiler.py
└── prompts/
    ├── __init__.py
    └── adaptive_learning_profiler.py
```

- Copy all files, update internal imports from `modules.adaptive_learner_modeling.*` → `modules.learner_profiler.*` (relative imports stay relative)

### C2. Update references

- **`main.py`**: `from modules.adaptive_learner_modeling import *` → `from modules.learner_profiler import *`
- **`tests/test_fslsm_update.py`**: `from modules.adaptive_learner_modeling.agents.adaptive_learning_profiler import ...` → `from modules.learner_profiler.agents.adaptive_learning_profiler import ...`
- **`modules/__init__.py`**: No reference to adaptive_learner_modeling exists there

### C3. Delete `modules/adaptive_learner_modeling/`

---

## Part D: Update Tests and Other References

### D1. `tests/test_fslsm_update.py` (line 14)

Change:
```python
from modules.adaptive_learner_modeling.agents.adaptive_learning_profiler import (
    update_learner_profile_with_llm,
)
```
To:
```python
from modules.learner_profiler.agents.adaptive_learning_profiler import (
    update_learner_profile_with_llm,
)
```

### D2. `modules/__init__.py`

Change:
```python
from .skill_gap_identification import SkillGapIdentifier, identify_skill_gap_with_llm, LearningGoalRefiner, refine_learning_goal_with_llm
```
To:
```python
from .skill_gap import SkillGapIdentifier, identify_skill_gap_with_llm, LearningGoalRefiner, refine_learning_goal_with_llm
```

### D3. `docs/user_flows_test_plan.md`

No changes needed — this file references test files and API endpoints only, not module import paths.

### D4. Other test files

`test_onboarding_api.py` mocks functions on `main` (e.g., `main.identify_skill_gap_with_llm`) — no module path references. No changes needed.

---

## Execution Order

1. Create `modules/learner_simulator/` — rename + add feedback simulators (A3)
2. Create `modules/learning_plan_generator/` (A1)
3. Create `modules/content_generator/` (A2)
4. Create `modules/skill_gap/` (B1)
5. Create `modules/learner_profiler/` (C1)
6. Update `main.py` imports — all at once (A4 + B2 + C2)
7. Update `modules/__init__.py` (D2)
8. Update `tests/test_fslsm_update.py` (D1)
9. Delete old directories: `personalized_resource_delivery/`, `learner_simulation/`, `skill_gap_identification/`, `adaptive_learner_modeling/`

## Verification

1. Run `python -c "from main import app"` to verify all imports resolve
2. Run existing tests: `pytest tests/`
3. Start the server (`python main.py`) and verify endpoints respond
