# Behavioral Patterns: Backend Endpoint for Real Computed Metrics

## Context

The learner profile's `behavioral_patterns` section currently displays LLM-hallucinated text (e.g., "Average of 3 logins per week"). Real behavioral data already exists in the user state blob persisted to the backend — specifically `session_learning_times` and `learned_skills_history`. This plan adds a `GET /behavioral-metrics/{user_id}` endpoint that computes real metrics from this stored data, making them available to the frontend profile page and reusable by the learner simulator and content generator evaluation in the future.

## Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `backend/main.py` | Modify | Add `GET /behavioral-metrics/{user_id}` endpoint |
| `backend/api_schemas.py` | Modify | Add `BehavioralMetricsResponse` schema |
| `backend/tests/test_behavioral_metrics.py` | Create | Tests for the new endpoint |

## Data Sources

The user state blob (stored via `PUT /user-state/{user_id}`, persisted to `data/user_states.json`) contains:

### `session_learning_times` — Dict keyed by `"{goal_id}-{session_id}"`
```python
{
    "0-0": {
        "start_time": 1708000000.123,   # Unix timestamp
        "end_time": 1708003600.456,     # Unix timestamp
        "trigger_time_list": [1708000000.123, 1708001200.789, ...]
        # First entry = session start. Subsequent entries = motivational triggers.
    },
    "0-1": { ... }
}
```
Written by `frontend/components/time_tracking.py` and `frontend/components/session_completion.py`.

### `learned_skills_history` — Dict keyed by goal_id
```python
{
    0: [0.0, 0.25, 0.50, 0.75],  # Mastery rate samples (0.0-1.0)
}
```
Sampled every 10 minutes by `frontend/main.py` (lines 190-221). Max 10 data points per goal.

### `goals` — List of goal dicts
Each goal has `"id"`, `"learning_path"` (list of sessions with `"if_learned"` flag), etc.

---

## Implementation Plan

### 1. Add response schema in `backend/api_schemas.py`

Add after the existing `UserStateRequest` class (line 200):

```python
class BehavioralMetricsResponse(BaseModel):
    user_id: str
    goal_id: Optional[int] = None
    sessions_completed: int
    total_sessions_in_path: int
    sessions_learned: int
    avg_session_duration_sec: float
    total_learning_time_sec: float
    motivational_triggers_count: int
    mastery_history: list
    latest_mastery_rate: Optional[float] = None
```

### 2. Add `GET /behavioral-metrics/{user_id}` endpoint in `backend/main.py`

Add after the user state endpoints (around line 206). The endpoint reads the user state blob and computes metrics.

```python
@app.get("/behavioral-metrics/{user_id}")
async def get_behavioral_metrics(user_id: str, goal_id: Optional[int] = None):
    state = store.get_user_state(user_id)
    if state is None:
        raise HTTPException(status_code=404, detail="No state found for this user_id")

    session_times = state.get("session_learning_times", {})
    mastery_history = state.get("learned_skills_history", {})
    goals = state.get("goals", [])

    # Filter sessions for the requested goal (keys are "{goal_id}-{session_id}")
    prefix = f"{goal_id}-" if goal_id is not None else None
    completed = []
    total_triggers = 0
    for key, times in session_times.items():
        if not isinstance(times, dict):
            continue
        if prefix and not str(key).startswith(prefix):
            continue
        start = times.get("start_time")
        end = times.get("end_time")
        if start is not None and end is not None:
            completed.append(max(end - start, 0.0))
        triggers = times.get("trigger_time_list", [])
        if len(triggers) > 1:
            total_triggers += len(triggers) - 1

    # Session completion from learning_path
    total_in_path = 0
    sessions_learned = 0
    if goal_id is not None:
        for g in goals:
            if isinstance(g, dict) and g.get("id") == goal_id:
                path = g.get("learning_path", [])
                total_in_path = len(path)
                sessions_learned = sum(1 for s in path if isinstance(s, dict) and s.get("if_learned"))
                break

    # Mastery history (keys may be int or str depending on serialization)
    history = []
    if isinstance(mastery_history, dict) and goal_id is not None:
        history = mastery_history.get(str(goal_id), mastery_history.get(goal_id, []))
    if not isinstance(history, list):
        history = []

    total_duration = sum(completed)
    avg_duration = total_duration / len(completed) if completed else 0.0

    return {
        "user_id": user_id,
        "goal_id": goal_id,
        "sessions_completed": len(completed),
        "total_sessions_in_path": total_in_path,
        "sessions_learned": sessions_learned,
        "avg_session_duration_sec": round(avg_duration, 1),
        "total_learning_time_sec": round(total_duration, 1),
        "motivational_triggers_count": total_triggers,
        "mastery_history": history,
        "latest_mastery_rate": history[-1] if history else None,
    }
```

### 3. Create `backend/tests/test_behavioral_metrics.py`

Use the same patterns as `test_user_state.py`: pytest fixtures with `monkeypatch` + `tmp_path` for store isolation, FastAPI `TestClient`.

```python
import pytest
import json
from fastapi.testclient import TestClient
from utils import store


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_USER_STATES_PATH", data_dir / "user_states.json")
    monkeypatch.setattr(store, "_user_states", {})
    store._USER_STATES_PATH = data_dir / "user_states.json"


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


class TestBehavioralMetrics:

    def test_no_state_returns_404(self, client):
        resp = client.get("/behavioral-metrics/unknown_user")
        assert resp.status_code == 404

    def test_empty_state_returns_zeros(self, client):
        client.put("/user-state/alice", json={"state": {}})
        resp = client.get("/behavioral-metrics/alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions_completed"] == 0
        assert data["avg_session_duration_sec"] == 0.0
        assert data["total_learning_time_sec"] == 0.0
        assert data["motivational_triggers_count"] == 0
        assert data["mastery_history"] == []
        assert data["latest_mastery_rate"] is None

    def test_completed_sessions_computed(self, client):
        state = {
            "session_learning_times": {
                "0-0": {"start_time": 1000.0, "end_time": 2800.0, "trigger_time_list": [1000.0]},
                "0-1": {"start_time": 3000.0, "end_time": 4200.0, "trigger_time_list": [3000.0]},
            }
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["sessions_completed"] == 2
        assert data["total_learning_time_sec"] == 3000.0  # 1800 + 1200
        assert data["avg_session_duration_sec"] == 1500.0  # 3000 / 2

    def test_goal_filter(self, client):
        state = {
            "session_learning_times": {
                "0-0": {"start_time": 1000.0, "end_time": 2000.0, "trigger_time_list": [1000.0]},
                "1-0": {"start_time": 3000.0, "end_time": 4000.0, "trigger_time_list": [3000.0]},
            }
        }
        client.put("/user-state/alice", json={"state": state})
        # Goal 0 only
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        assert resp.json()["sessions_completed"] == 1
        # Goal 1 only
        resp = client.get("/behavioral-metrics/alice?goal_id=1")
        assert resp.json()["sessions_completed"] == 1

    def test_trigger_count(self, client):
        state = {
            "session_learning_times": {
                "0-0": {
                    "start_time": 1000.0,
                    "end_time": 2000.0,
                    "trigger_time_list": [1000.0, 1180.0, 1360.0],  # 2 actual triggers
                },
            }
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        assert resp.json()["motivational_triggers_count"] == 2

    def test_mastery_history(self, client):
        state = {
            "learned_skills_history": {"0": [0.0, 0.25, 0.5]},
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["mastery_history"] == [0.0, 0.25, 0.5]
        assert data["latest_mastery_rate"] == 0.5

    def test_sessions_learned_count(self, client):
        state = {
            "goals": [
                {
                    "id": 0,
                    "learning_path": [
                        {"if_learned": True},
                        {"if_learned": False},
                        {"if_learned": True},
                    ],
                }
            ],
        }
        client.put("/user-state/alice", json={"state": state})
        resp = client.get("/behavioral-metrics/alice?goal_id=0")
        data = resp.json()
        assert data["total_sessions_in_path"] == 3
        assert data["sessions_learned"] == 2
```

---

## Verification

1. Run `python -m pytest backend/tests/test_behavioral_metrics.py -v` — all 7 tests pass
2. Run `python -m pytest backend/tests/ -v` — all existing tests still pass (no regressions)
3. Start the backend, store some user state, then `curl http://localhost:8000/behavioral-metrics/TestUser?goal_id=0` — verify computed metrics
