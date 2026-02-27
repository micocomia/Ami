"""Tests for cross-goal profile sync (merge_shared_profile_fields and /sync-profile endpoint).

Run from the repo root:
    python -m pytest backend/tests/test_profile_sync.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store


# ---------------------------------------------------------------------------
# Fixtures – redirect store to a temporary directory (same pattern as test_store_and_auth.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point store module at a temp directory and reset its in-memory state."""
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_GOALS_PATH", data_dir / "goals.json")
    monkeypatch.setattr(store, "_LEARNING_CONTENT_PATH", data_dir / "learning_content.json")
    monkeypatch.setattr(store, "_SESSION_ACTIVITY_PATH", data_dir / "session_activity.json")
    monkeypatch.setattr(store, "_MASTERY_HISTORY_PATH", data_dir / "mastery_history.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_goals", {})
    monkeypatch.setattr(store, "_learning_content_cache", {})
    monkeypatch.setattr(store, "_session_activity", {})
    monkeypatch.setattr(store, "_mastery_history", {})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(
    mastered=None,
    in_progress=None,
    learning_preferences=None,
    behavioral_patterns=None,
    overall_progress=0.0,
    learning_goal="Test Goal",
):
    """Build a minimal learner profile dict."""
    return {
        "learning_goal": learning_goal,
        "cognitive_status": {
            "mastered_skills": mastered or [],
            "in_progress_skills": in_progress or [],
            "overall_progress": overall_progress,
        },
        "learning_preferences": learning_preferences,
        "behavioral_patterns": behavioral_patterns,
    }


def _skill(name, proficiency="intermediate"):
    return {"name": name, "proficiency_level": proficiency}


# ===================================================================
# TestMergeSharedProfileFields
# ===================================================================

class TestMergeSharedProfileFields:

    def test_merge_no_other_goals(self):
        """Single goal -> profile returned unchanged."""
        profile = _make_profile(
            mastered=[_skill("Python", "intermediate")],
            in_progress=[_skill("Docker", "beginner")],
        )
        store.upsert_profile("alice", 0, profile)

        result = store.merge_shared_profile_fields("alice", 0)
        assert result is not None
        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        assert mastered_names == {"Python"}
        in_progress_names = {s["name"] for s in result["cognitive_status"]["in_progress_skills"]}
        assert in_progress_names == {"Docker"}

    def test_merge_mastered_skills_union(self):
        """Goal A has Skill X mastered, Goal B has Skill Y -> target gets both."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python")]))
        store.upsert_profile("alice", 1, _make_profile(mastered=[_skill("Docker")]))

        result = store.merge_shared_profile_fields("alice", 1)
        mastered_names = {s["name"] for s in result["cognitive_status"]["mastered_skills"]}
        assert mastered_names == {"Python", "Docker"}

    def test_merge_highest_proficiency_wins(self):
        """Same skill at intermediate in Goal A, advanced in Goal B -> advanced kept."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python", "advanced")]))
        store.upsert_profile("alice", 1, _make_profile(mastered=[_skill("Python", "intermediate")]))

        result = store.merge_shared_profile_fields("alice", 1)
        python_skill = next(
            s for s in result["cognitive_status"]["mastered_skills"] if s["name"] == "Python"
        )
        assert python_skill["proficiency_level"] == "advanced"

    def test_merge_preferences_propagate(self):
        """FSLSM from Goal A appears in Goal B after merge."""
        prefs = {
            "fslsm_dimensions": {
                "fslsm_processing": -0.7,
                "fslsm_perception": 0.5,
                "fslsm_input": -0.5,
                "fslsm_understanding": 0.3,
            }
        }
        store.upsert_profile("alice", 0, _make_profile(learning_preferences=prefs))
        store.upsert_profile("alice", 1, _make_profile())  # no preferences

        result = store.merge_shared_profile_fields("alice", 1)
        assert result["learning_preferences"] is not None
        assert result["learning_preferences"]["fslsm_dimensions"]["fslsm_processing"] == -0.7

    def test_merge_behavioral_propagate(self):
        """behavioral_patterns from Goal A appear in Goal B after merge."""
        behavioral = {"engagement_level": "high", "session_frequency": "daily"}
        store.upsert_profile("alice", 0, _make_profile(behavioral_patterns=behavioral))
        store.upsert_profile("alice", 1, _make_profile())

        result = store.merge_shared_profile_fields("alice", 1)
        assert result["behavioral_patterns"] is not None
        assert result["behavioral_patterns"]["engagement_level"] == "high"

    def test_merge_removes_mastered_from_in_progress(self):
        """Skill mastered in Goal A is removed from Goal B's in_progress_skills."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python", "advanced")]))
        store.upsert_profile(
            "alice", 1,
            _make_profile(in_progress=[_skill("Python", "beginner"), _skill("Docker", "beginner")]),
        )

        result = store.merge_shared_profile_fields("alice", 1)
        in_progress_names = {s["name"] for s in result["cognitive_status"]["in_progress_skills"]}
        assert "Python" not in in_progress_names
        assert "Docker" in in_progress_names

    def test_merge_recalculates_progress(self):
        """overall_progress = mastered / (mastered + in_progress) * 100."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python"), _skill("Git")]))
        store.upsert_profile(
            "alice", 1,
            _make_profile(
                mastered=[_skill("Docker")],
                in_progress=[_skill("Python", "beginner"), _skill("Kubernetes", "beginner")],
            ),
        )

        result = store.merge_shared_profile_fields("alice", 1)
        # After merge: mastered = {Python, Git, Docker} = 3; in_progress = {Kubernetes} = 1
        # (Python removed from in_progress because it's mastered)
        assert result["cognitive_status"]["overall_progress"] == 75.0

    def test_merge_persists(self):
        """After merge, get_profile() returns the merged version."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python")]))
        store.upsert_profile("alice", 1, _make_profile(mastered=[_skill("Docker")]))

        store.merge_shared_profile_fields("alice", 1)

        persisted = store.get_profile("alice", 1)
        mastered_names = {s["name"] for s in persisted["cognitive_status"]["mastered_skills"]}
        assert mastered_names == {"Python", "Docker"}


# ===================================================================
# TestSyncEndpoint
# ===================================================================

class TestSyncEndpoint:

    @pytest.fixture()
    def client(self):
        """Create a TestClient for the FastAPI app with isolated store."""
        # Import here so the app module's startup doesn't interfere
        from fastapi.testclient import TestClient
        # Lazy import to avoid heavy module-level imports
        import main as app_module
        return TestClient(app_module.app)

    def test_sync_endpoint_returns_merged(self, client):
        """POST /sync-profile/{uid}/{gid} returns merged profile."""
        store.upsert_profile("alice", 0, _make_profile(mastered=[_skill("Python")]))
        store.upsert_profile("alice", 1, _make_profile(mastered=[_skill("Docker")]))

        resp = client.post("/sync-profile/alice/1")
        assert resp.status_code == 200
        data = resp.json()
        mastered_names = {s["name"] for s in data["learner_profile"]["cognitive_status"]["mastered_skills"]}
        assert mastered_names == {"Python", "Docker"}

    def test_sync_endpoint_404_no_profile(self, client):
        """Returns 404 if target goal has no profile."""
        resp = client.post("/sync-profile/alice/99")
        assert resp.status_code == 404
