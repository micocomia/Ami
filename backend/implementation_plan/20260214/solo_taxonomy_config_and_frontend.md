# SOLO Taxonomy: Config Endpoint & Frontend Changes

## Context

The `GET /config` endpoint serves `skill_levels` to the frontend. The frontend uses this to render pill selectors, radar chart axes, and level mappings. Both the backend config and the frontend's local fallback must include `expert`.

---

## Files to Modify

### 1. `backend/main.py`

**Update `APP_CONFIG`** (line 322):

Change:
```python
"skill_levels": ["unlearned", "beginner", "intermediate", "advanced"],
```
To:
```python
"skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
```

### 2. `frontend/utils/request_api.py`

**Update `_LOCAL_APP_CONFIG`** (line 583):

Change:
```python
"skill_levels": ["unlearned", "beginner", "intermediate", "advanced"],
```
To:
```python
"skill_levels": ["unlearned", "beginner", "intermediate", "advanced", "expert"],
```

This is the local fallback used when the backend is unreachable.

---

## Frontend Components That Auto-Update (No Changes Needed)

These components dynamically fetch levels from `get_app_config()["skill_levels"]`, so they will automatically show `expert` once the config is updated:

- **`frontend/components/gap_identification.py`** (line 23): `levels = get_app_config()["skill_levels"]` — feeds the Required Level and Current Level pill selectors
- **`frontend/components/skill_info.py`** (line 36): `levels = get_app_config()["skill_levels"]` — used for skill info display
- **`frontend/pages/dashboard.py`** (lines 105-144): `skill_levels = get_app_config()["skill_levels"]` — builds `level_map` for radar chart. The chart axis will automatically show 5 ticks (0=Unlearned through 4=Expert) and the radar range will be [0, 4] instead of [0, 3]

## Frontend Components That Display Proficiency From API (No Changes Needed)

These display proficiency values from API responses using `.capitalize()` — they'll show "Expert" naturally:

- **`frontend/components/skill_info.py`** (line 19): `skill['proficiency_level'].capitalize()` for mastered skills
- **`frontend/components/skill_info.py`** (lines 31-32): displays `required_proficiency_level` and `current_proficiency_level` for in-progress skills

## Frontend Components Unaffected

- **Color mappings** in `gap_identification.py`, `skill_info.py`, `learning_path.py` are based on gap/learned status, not individual proficiency levels — no changes needed
- **`goal_management.py`** and **`main.py`** count mastered vs in-progress skills — level-agnostic, no changes needed

---

## Verification

1. **Backend**: `curl http://localhost:8000/config | python -m json.tool` — `skill_levels` should show 5 items
2. **Frontend pill selectors**: On the Skill Gap page, the Required Level and Current Level pill selectors should show 5 options: Unlearned, Beginner, Intermediate, Advanced, Expert
3. **Dashboard radar chart**: Should show 5 tick marks on the radial axis (0=Unlearned through 4=Expert)
4. **Fallback test**: Stop the backend, reload the frontend — the local fallback should also show 5 levels
