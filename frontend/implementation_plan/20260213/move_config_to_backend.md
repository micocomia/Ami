# Move Frontend Hardcoded Data to Backend `GET /config` Endpoint

## Context
Multiple pieces of domain data and configuration are hardcoded across the frontend. Moving them to a single backend `GET /config` endpoint makes the data available to any frontend (Streamlit now, React later) from one source of truth.

## What moves to the backend

| Item | Current location(s) | Config key |
|------|---------------------|------------|
| Skill levels | `gap_identification.py:23`, `skill_info.py:35`, `dashboard.py:104,142` | `skill_levels` |
| FSLSM thresholds + labels | `learner_profile.py:143-169` | `fslsm_thresholds` |
| Default session count | `learning_path.py:147` (hardcoded `8`) | `default_session_count` |
| Default LLM type | 15 function sigs in `request_api.py` (`"gpt4o"`) | `default_llm_type` |
| Default method name | 15 function sigs in `request_api.py` (`"genmentor"`) | `default_method_name` |
| Motivational trigger interval | `knowledge_document.py:89` (`60 * 3`) | `motivational_trigger_interval_secs` |
| Max refinement iterations | `learning_path.py:226` (`[1,2,3,4,5]`), `request_api.py:429` (`max_iterations=2`) | `max_refinement_iterations` |

## Files modified

### Backend
- **`backend/main.py`** — Added `APP_CONFIG` dict and `GET /config` endpoint

### Frontend
- **`frontend/utils/request_api.py`** — Added `get_app_config()` function with local fallback; updated all 15 function signatures to pull defaults from config
- **`frontend/utils/state.py`** — Uses config `default_llm_type` as fallback for `llm_type`
- **`frontend/components/gap_identification.py`** — Replaced hardcoded `levels` with config fetch
- **`frontend/components/skill_info.py`** — Replaced hardcoded `levels` with config fetch
- **`frontend/pages/dashboard.py`** — Replaced hardcoded `level_map` and `ticktext` with config fetch
- **`frontend/pages/learner_profile.py`** — Replaced hardcoded FSLSM threshold logic with config-driven logic
- **`frontend/pages/learning_path.py`** — Replaced hardcoded `session_count=8` and iteration options with config
- **`frontend/pages/knowledge_document.py`** — Replaced hardcoded `trigger_interval` with config

## Verification
1. Start backend, hit `GET /config` — verify JSON response contains all keys
2. Start frontend with backend running — verify config is fetched
3. Start frontend with `use_mock_data=True` — verify local fallback works
4. Test skill gap page — levels should render correctly
5. Test learner profile page — FSLSM descriptions should render correctly
6. Test learning path scheduling — should use `default_session_count` from config
7. Test auto-refine iterations dropdown — should show `range(1, max+1)`
8. Test knowledge document page — motivational toasts should appear at configured interval
