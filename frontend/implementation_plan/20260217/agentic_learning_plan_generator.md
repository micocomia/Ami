# Frontend: Agentic Learning Plan Generator

## Context

The frontend previously had manual "Simulate Feedback" / "Refine Path" / "Auto-Refine" buttons that called separate backend endpoints. With the agentic backend, these are now internal to the auto-refinement loop. The frontend is updated to:

1. Call the new agentic endpoint for plan generation
2. Display auto-evaluation quality results (read-only)
3. Show retrieved course content sources
4. Trigger plan adaptation after mastery failures or preference changes

## Changes Made

### Step 1: Updated API Client (`frontend/utils/request_api.py`)

Added new functions:
- `schedule_learning_path_agentic()` -- calls `POST /schedule-learning-path-agentic`, returns `{learning_path, agent_metadata}`
- `adapt_learning_path()` -- calls `POST /adapt-learning-path`, returns `{learning_path, agent_metadata}`
- Updated `schedule_learning_path()` to return `{learning_path, retrieved_sources}` (includes sources from backend)

Added API name mappings:
- `schedule_path_agentic` -> `schedule-learning-path-agentic`
- `adapt_path` -> `adapt-learning-path`

### Step 2: Replaced Feedback Section with Quality Display (`frontend/pages/learning_path.py`)

Removed:
- `render_path_feedback_section()` -- the Simulate Feedback / Refine Path / Auto-Refine buttons
- Imports for `simulate_path_feedback`, `refine_learning_path_with_feedback`, `iterative_refine_learning_path`

Added:
- `render_retrieval_sources_banner()` -- shows course content sources that grounded the plan (reuses `format_citation` pattern from gap_identification)
- `render_plan_quality_section()` -- read-only display of auto-evaluation results:
  - Plan Quality: PASS/NEEDS REVIEW
  - Feedback summary (Progression, Engagement, Personalization)
  - Refinement iterations count
  - Issues list if quality needs review
- `render_adaptation_section()` -- shows adaptation suggestion banner when `adaptation_suggested_{goal_id}` is set in session state, calls `/adapt-learning-path` on click

Updated plan generation flow:
- Calls `schedule_learning_path_agentic()` instead of `schedule_learning_path()`
- Stores `plan_agent_metadata` and `retrieved_sources` in goal dict

### Step 3: Adaptation UI After Mastery Evaluation (`frontend/pages/knowledge_document.py`)

- After quiz submission, if backend returns `plan_adaptation_suggested: true`, sets `adaptation_suggested_{goal_id}` flag in session state
- Banner appears on Learning Path page via `render_adaptation_section()`

## Files Modified

- `frontend/utils/request_api.py` (modified -- new API functions)
- `frontend/pages/learning_path.py` (modified -- replaced feedback section)
- `frontend/pages/knowledge_document.py` (modified -- adaptation flag)
