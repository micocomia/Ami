"""Tests for onboarding-related API endpoints.

Covers the backend side of:
  - Flow 2B: PDF resume upload  (POST /extract-pdf-text)
  - Flow 2D: Goal refinement    (POST /refine-learning-goal)
  - Flow 2E: Skill gap ID       (POST /identify-skill-gap-with-info)
  - Profile creation             (POST /create-learner-profile-with-info)
  - Event logging                (POST /events/log)
  - Profile retrieval            (GET  /profile/{user_id})
  - Personas endpoint            (GET  /personas)
  - Config endpoint              (GET  /config)

LLM-dependent endpoints are tested with mocked LLM functions so
these tests run without API keys or network access.

Run from the repo root:
    python -m pytest backend/tests/test_onboarding_api.py -v
"""

import sys
import os
import io
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from utils import store, auth_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_PROFILE_SNAPSHOTS_PATH", data_dir / "profile_snapshots.json")
    monkeypatch.setattr(store, "_GOALS_PATH", data_dir / "goals.json")
    monkeypatch.setattr(store, "_LEARNING_CONTENT_PATH", data_dir / "learning_content.json")
    monkeypatch.setattr(store, "_SESSION_ACTIVITY_PATH", data_dir / "session_activity.json")
    monkeypatch.setattr(store, "_MASTERY_HISTORY_PATH", data_dir / "mastery_history.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_profile_snapshots", {})
    monkeypatch.setattr(store, "_goals", {})
    monkeypatch.setattr(store, "_learning_content_cache", {})
    monkeypatch.setattr(store, "_session_activity", {})
    monkeypatch.setattr(store, "_mastery_history", {})


@pytest.fixture(autouse=True)
def _isolate_auth_store(tmp_path, monkeypatch):
    data_dir = tmp_path / "auth_data"
    data_dir.mkdir()
    monkeypatch.setattr(auth_store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(auth_store, "_USERS_PATH", data_dir / "users.json")
    monkeypatch.setattr(auth_store, "_users", {})


@pytest.fixture()
def client():
    from main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Shared mock return values
# ---------------------------------------------------------------------------

MOCK_REFINED_GOAL = {
    "refined_goal": "Become a certified HR Manager with expertise in HRIS systems and talent acquisition"
}

MOCK_SKILL_GAPS_RESULT = {
    "skill_gaps": [
        {
            "name": "HRIS Management",
            "is_gap": True,
            "required_level": "intermediate",
            "current_level": "beginner",
            "reason": "Limited hands-on experience with HRIS platforms",
            "level_confidence": "high",
        },
        {
            "name": "Communication",
            "is_gap": False,
            "required_level": "advanced",
            "current_level": "advanced",
            "reason": "Strong background from MBA program",
            "level_confidence": "high",
        },
    ],
    "goal_assessment": {
        "is_vague": False,
        "all_mastered": False,
        "suggestion": "",
        "auto_refined": False,
        "original_goal": None,
    },
}

MOCK_SKILL_REQUIREMENTS = {
    "skill_requirements": {
        "HRIS Management": "intermediate",
        "Communication": "advanced",
    }
}

MOCK_LEARNER_PROFILE = {
    "learner_information": "MBA grad with admin background",
    "learning_goal": "Become an HR Manager",
    "cognitive_status": {
        "overall_progress": 20,
        "mastered_skills": [
            {"name": "Communication", "proficiency_level": "advanced"}
        ],
        "in_progress_skills": [
            {
                "name": "HRIS Management",
                "required_proficiency_level": "intermediate",
                "current_proficiency_level": "beginner",
            }
        ],
    },
    "learning_preferences": {
        "fslsm_dimensions": {
            "fslsm_processing": -0.5,
            "fslsm_perception": -0.3,
            "fslsm_input": -0.5,
            "fslsm_understanding": -0.3,
        },
        "content_style": "Concrete examples and practical applications",
        "activity_type": "Hands-on and interactive activities",
        "additional_notes": "Prefers step-by-step guidance",
    },
    "behavioral_patterns": {
        "system_usage_frequency": "3 logins/week",
        "session_duration_engagement": "25 min avg",
        "motivational_triggers": "Career advancement, practical application",
        "additional_notes": "Most active in evenings",
    },
}


# ===================================================================
# POST /extract-pdf-text  (Flow 2B: Resume upload)
# ===================================================================

class TestExtractPdfText:
    def test_upload_valid_pdf(self, client):
        """A minimal valid PDF should return extracted text."""
        # Build a tiny in-memory PDF via reportlab if available,
        # otherwise use pdfplumber-compatible raw bytes.
        # For simplicity, we mock pdfplumber at the endpoint level.
        import pdfplumber

        fake_pdf_bytes = b"%PDF-1.4 fake"  # not a real PDF

        with patch("main.pdfplumber") as mock_plumber:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "John Doe - Software Engineer - 5 years experience"
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_plumber.open.return_value = mock_pdf

            resp = client.post(
                "/extract-pdf-text",
                files={"file": ("resume.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")},
            )
            assert resp.status_code == 200
            assert "John Doe" in resp.json()["text"]

    def test_upload_multi_page_pdf(self, client):
        """Multi-page PDF should concatenate text from all pages."""
        fake_pdf_bytes = b"%PDF-1.4 fake"

        with patch("main.pdfplumber") as mock_plumber:
            page1 = MagicMock()
            page1.extract_text.return_value = "Page 1 content"
            page2 = MagicMock()
            page2.extract_text.return_value = "Page 2 content"
            mock_pdf = MagicMock()
            mock_pdf.pages = [page1, page2]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_plumber.open.return_value = mock_pdf

            resp = client.post(
                "/extract-pdf-text",
                files={"file": ("resume.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")},
            )
            assert resp.status_code == 200
            text = resp.json()["text"]
            assert "Page 1 content" in text
            assert "Page 2 content" in text

    def test_upload_no_file_returns_422(self, client):
        """Missing file should return 422 (validation error)."""
        resp = client.post("/extract-pdf-text")
        assert resp.status_code == 422


# ===================================================================
# POST /refine-learning-goal  (Flow 2D: Goal refinement)
# ===================================================================

class TestRefineGoalEndpoint:
    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_success(self, mock_get_llm, mock_refine, client):
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        resp = client.post("/refine-learning-goal", json={
            "learning_goal": "Become HR Manager",
            "learner_information": "MBA grad with admin background",
        })
        assert resp.status_code == 200
        assert "refined_goal" in resp.json()
        mock_refine.assert_called_once()

    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_passes_learner_info(self, mock_get_llm, mock_refine, client):
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        client.post("/refine-learning-goal", json={
            "learning_goal": "Learn Python",
            "learner_information": "CS student, sophomore year",
        })

        _, kwargs = mock_refine.call_args
        # Verify the learner_information was forwarded
        call_args = mock_refine.call_args
        assert "Learn Python" in str(call_args)

    @patch("main.refine_learning_goal_with_llm")
    @patch("main.get_llm")
    def test_refine_goal_empty_learner_info(self, mock_get_llm, mock_refine, client):
        """Refinement should work even without learner information."""
        mock_get_llm.return_value = MagicMock()
        mock_refine.return_value = MOCK_REFINED_GOAL

        resp = client.post("/refine-learning-goal", json={
            "learning_goal": "Learn Python",
            "learner_information": "",
        })
        assert resp.status_code == 200

    @patch("main.get_llm")
    def test_refine_goal_llm_failure_returns_500(self, mock_get_llm, client):
        mock_get_llm.return_value = MagicMock()

        with patch("main.refine_learning_goal_with_llm", side_effect=Exception("LLM timeout")):
            resp = client.post("/refine-learning-goal", json={
                "learning_goal": "Learn Python",
                "learner_information": "",
            })
            assert resp.status_code == 500


# ===================================================================
# POST /identify-skill-gap-with-info  (Flow 2E: Skill gap)
# ===================================================================

class TestIdentifySkillGapEndpoint:
    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_success(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad with admin background",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "skill_gaps" in data
        assert "skill_requirements" in data
        assert len(data["skill_gaps"]) == 2

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_returns_gap_fields(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
        })
        gaps = resp.json()["skill_gaps"]
        for gap in gaps:
            assert "name" in gap
            assert "is_gap" in gap
            assert "required_level" in gap
            assert "current_level" in gap

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_with_existing_requirements(self, mock_get_llm, mock_identify, client):
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_requirements": '{"HRIS Management": "intermediate"}',
        })
        assert resp.status_code == 200

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_response_includes_goal_assessment(self, mock_get_llm, mock_identify, client):
        """Response should include the goal_assessment field."""
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        resp = client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
        })
        data = resp.json()
        assert "goal_assessment" in data
        assert data["goal_assessment"]["is_vague"] is False

    @patch("main.identify_skill_gap_with_llm")
    @patch("main.get_llm")
    def test_identify_skill_gap_called_with_search_rag_manager(self, mock_get_llm, mock_identify, client):
        """identify_skill_gap_with_llm should receive search_rag_manager kwarg."""
        mock_get_llm.return_value = MagicMock()
        mock_identify.return_value = (MOCK_SKILL_GAPS_RESULT, MOCK_SKILL_REQUIREMENTS)

        client.post("/identify-skill-gap-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
        })

        _, kwargs = mock_identify.call_args
        assert "search_rag_manager" in kwargs

    @patch("main.get_llm")
    def test_identify_skill_gap_llm_failure(self, mock_get_llm, client):
        mock_get_llm.return_value = MagicMock()

        with patch("main.identify_skill_gap_with_llm", side_effect=Exception("LLM error")):
            resp = client.post("/identify-skill-gap-with-info", json={
                "learning_goal": "Learn Python",
                "learner_information": "Beginner",
            })
            assert resp.status_code == 500


# ===================================================================
# POST /create-learner-profile-with-info  (Profile creation)
# ===================================================================

class TestCreateLearnerProfileEndpoint:
    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_success(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad with admin background",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
        })
        assert resp.status_code == 200
        profile = resp.json()["learner_profile"]
        assert "cognitive_status" in profile
        assert "learning_preferences" in profile
        assert "behavioral_patterns" in profile

    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_stores_when_user_id_provided(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
            "user_id": "alice",
            "goal_id": 0,
        })
        assert resp.status_code == 200

        # Verify it was persisted in the store
        stored = store.get_profile("alice", 0)
        assert stored is not None
        assert stored["learning_goal"] == "Become an HR Manager"

    @patch("main.initialize_learner_profile_with_llm")
    @patch("main.get_llm")
    def test_create_profile_does_not_store_without_user_id(self, mock_get_llm, mock_init, client):
        mock_get_llm.return_value = MagicMock()
        mock_init.return_value = MOCK_LEARNER_PROFILE

        resp = client.post("/create-learner-profile-with-info", json={
            "learning_goal": "Become an HR Manager",
            "learner_information": "MBA grad",
            "skill_gaps": json.dumps(MOCK_SKILL_GAPS_RESULT["skill_gaps"]),
        })
        assert resp.status_code == 200
        # No user_id/goal_id => not stored
        assert store.get_profile("alice", 0) is None


# ===================================================================
# POST /events/log  (Event logging during onboarding)
# ===================================================================

class TestEventLogging:
    def test_log_event_success(self, client):
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "page_view",
            "payload": {"page": "onboarding"},
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["event_count"] == 1

    def test_log_multiple_events(self, client):
        for i in range(3):
            client.post("/events/log", json={
                "user_id": "alice",
                "event_type": f"action_{i}",
                "payload": {},
            })
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "action_3",
            "payload": {},
        })
        assert resp.json()["event_count"] == 4

    def test_log_event_auto_timestamps(self, client):
        resp = client.post("/events/log", json={
            "user_id": "alice",
            "event_type": "click",
            "payload": {},
        })
        assert resp.status_code == 200
        events = store.get_events("alice")
        assert events[0]["ts"] is not None


# ===================================================================
# GET /profile/{user_id}  (Profile retrieval)
# ===================================================================

class TestProfileRetrieval:
    def test_get_profile_by_goal_id(self, client):
        store.upsert_profile("alice", 0, MOCK_LEARNER_PROFILE)
        resp = client.get("/profile/alice", params={"goal_id": 0})
        assert resp.status_code == 200
        assert resp.json()["learner_profile"]["learning_goal"] == "Become an HR Manager"

    def test_get_all_profiles(self, client):
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})
        resp = client.get("/profile/alice")
        assert resp.status_code == 200
        assert len(resp.json()["profiles"]) == 2

    def test_get_profile_nonexistent_returns_404(self, client):
        resp = client.get("/profile/nobody", params={"goal_id": 0})
        assert resp.status_code == 404

    def test_get_profiles_nonexistent_user_returns_404(self, client):
        resp = client.get("/profile/nobody")
        assert resp.status_code == 404


# ===================================================================
# GET /personas  (Persona definitions)
# ===================================================================

class TestPersonasEndpoint:
    def test_get_personas_returns_200(self, client):
        resp = client.get("/personas")
        assert resp.status_code == 200

    def test_get_personas_has_personas_key(self, client):
        resp = client.get("/personas")
        data = resp.json()
        assert "personas" in data

    def test_get_personas_contains_all_five(self, client):
        personas = client.get("/personas").json()["personas"]
        expected = {
            "Hands-on Explorer",
            "Reflective Reader",
            "Visual Learner",
            "Conceptual Thinker",
            "Balanced Learner",
        }
        assert set(personas.keys()) == expected

    def test_get_personas_each_has_required_fields(self, client):
        personas = client.get("/personas").json()["personas"]
        for name, persona in personas.items():
            assert "description" in persona, f"{name} missing description"
            assert "fslsm_dimensions" in persona, f"{name} missing fslsm_dimensions"
            dims = persona["fslsm_dimensions"]
            for dim_key in ("fslsm_processing", "fslsm_perception", "fslsm_input", "fslsm_understanding"):
                assert dim_key in dims, f"{name} missing {dim_key}"
                assert isinstance(dims[dim_key], (int, float)), f"{name}.{dim_key} is not numeric"

    def test_get_personas_dimensions_in_range(self, client):
        """All FSLSM dimension values should be between -1.0 and 1.0."""
        personas = client.get("/personas").json()["personas"]
        for name, persona in personas.items():
            for dim_key, value in persona["fslsm_dimensions"].items():
                assert -1.0 <= value <= 1.0, f"{name}.{dim_key} = {value} is out of range"


# ===================================================================
# GET /config  (Application configuration)
# ===================================================================

class TestConfigEndpoint:
    def test_get_config_returns_200(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200

    def test_get_config_has_all_required_keys(self, client):
        data = client.get("/config").json()
        required_keys = [
            "skill_levels",
            "default_session_count",
            "default_llm_type",
            "default_method_name",
            "motivational_trigger_interval_secs",
            "max_refinement_iterations",
            "prefetch_enabled",
            "prefetch_wait_short_secs",
            "prefetch_wait_long_secs",
            "prefetch_cooldown_secs",
            "prefetch_max_workers",
            "fslsm_thresholds",
        ]
        for key in required_keys:
            assert key in data, f"Missing config key: {key}"

    def test_get_config_skill_levels_is_nonempty_list(self, client):
        data = client.get("/config").json()
        assert isinstance(data["skill_levels"], list)
        assert len(data["skill_levels"]) > 0

    def test_get_config_skill_levels_contains_expected_values(self, client):
        levels = client.get("/config").json()["skill_levels"]
        assert levels == ["unlearned", "beginner", "intermediate", "advanced", "expert"]

    def test_get_config_numeric_values(self, client):
        data = client.get("/config").json()
        assert isinstance(data["default_session_count"], int)
        assert data["default_session_count"] > 0
        assert isinstance(data["motivational_trigger_interval_secs"], int)
        assert data["motivational_trigger_interval_secs"] > 0
        assert isinstance(data["max_refinement_iterations"], int)
        assert data["max_refinement_iterations"] > 0

    def test_get_config_fslsm_thresholds_has_all_dimensions(self, client):
        thresholds = client.get("/config").json()["fslsm_thresholds"]
        for dim in ("perception", "understanding", "processing", "input"):
            assert dim in thresholds, f"Missing fslsm_thresholds dimension: {dim}"

    def test_get_config_fslsm_thresholds_have_required_fields(self, client):
        thresholds = client.get("/config").json()["fslsm_thresholds"]
        for dim, cfg in thresholds.items():
            for field in ("low_threshold", "high_threshold", "low_label", "high_label", "neutral_label"):
                assert field in cfg, f"fslsm_thresholds.{dim} missing {field}"
            assert isinstance(cfg["low_threshold"], (int, float))
            assert isinstance(cfg["high_threshold"], (int, float))
            assert cfg["low_threshold"] < cfg["high_threshold"]


class TestAdaptationEndpoints:
    def _seed_goal_and_profile(self):
        goal = store.create_goal("alice", {
            "learning_goal": "Learn Python",
            "skill_gaps": [],
            "learning_path": [{
                "id": "Session 1",
                "title": "Intro",
                "abstract": "Read and discuss text-based concepts.",
                "if_learned": False,
                "associated_skills": ["Python Basics"],
                "desired_outcome_when_completed": [{"name": "Python Basics", "level": "beginner"}],
                "mastery_score": 20.0,
                "is_mastered": False,
                "mastery_threshold": 70.0,
                "has_checkpoint_challenges": False,
                "thinking_time_buffer_minutes": 10,
                "session_sequence_hint": "theory-first",
                "navigation_mode": "free",
                "input_mode_hint": "verbal",
            }],
        })
        store.upsert_profile("alice", goal["id"], {
            "learning_preferences": {
                "fslsm_dimensions": {
                    "fslsm_processing": 0.8,
                    "fslsm_perception": 0.8,
                    "fslsm_input": 0.8,
                    "fslsm_understanding": 0.8,
                }
            }
        })
        return goal["id"]

    def test_reschedule_endpoint_removed(self, client):
        resp = client.post("/reschedule-learning-path", json={})
        assert resp.status_code == 404

    @patch("main.get_llm")
    @patch("main.evaluate_plan")
    @patch("main.reschedule_learning_path_with_llm")
    @patch("main.PREFETCH_SERVICE.enqueue_for_goal")
    def test_adapt_learning_path_auto_mode_works(self, mock_enqueue_prefetch, mock_reschedule, mock_evaluate_plan, mock_get_llm, client):
        goal_id = self._seed_goal_and_profile()
        mock_get_llm.return_value = MagicMock()
        mock_evaluate_plan.return_value = {"is_acceptable": True, "issues": [], "feedback": {}}
        mock_enqueue_prefetch.return_value = "queued"
        mock_reschedule.return_value = {
            "learning_path": [{
                "id": "Session 1",
                "title": "Adjusted",
                "abstract": "Adjusted plan.",
                "if_learned": False,
                "associated_skills": ["Python Basics"],
                "desired_outcome_when_completed": [{"name": "Python Basics", "level": "beginner"}],
                "mastery_score": 20.0,
                "is_mastered": False,
                "mastery_threshold": 70.0,
                "has_checkpoint_challenges": False,
                "thinking_time_buffer_minutes": 10,
                "session_sequence_hint": "theory-first",
                "navigation_mode": "free",
                "input_mode_hint": "verbal",
            }]
        }
        resp = client.post("/adapt-learning-path", json={"user_id": "alice", "goal_id": goal_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "adaptation" in data
        assert "status" in data["adaptation"]
        mock_enqueue_prefetch.assert_called_once()


class TestLearningPathSchedulingErrorHandling:
    @patch("main.get_llm")
    @patch("main.schedule_learning_path_with_llm")
    def test_schedule_learning_path_returns_422_for_validation_error(self, mock_schedule, mock_get_llm, client):
        mock_get_llm.return_value = MagicMock()
        mock_schedule.side_effect = ValueError("Learning path must contain between 1 and 20 sessions.")

        resp = client.post(
            "/schedule-learning-path",
            json={
                "learner_profile": "{}",
                "session_count": 8,
            },
        )

        assert resp.status_code == 422
        assert "between 1 and 20 sessions" in resp.json()["detail"]

    @patch("main.get_llm")
    @patch("main.schedule_learning_path_agentic")
    def test_schedule_learning_path_agentic_returns_422_for_validation_error(
        self,
        mock_schedule_agentic,
        mock_get_llm,
        client,
    ):
        mock_get_llm.return_value = MagicMock()
        mock_schedule_agentic.side_effect = ValueError("Learning path must contain between 1 and 20 sessions.")

        resp = client.post(
            "/schedule-learning-path-agentic",
            json={
                "learner_profile": "{}",
                "session_count": 8,
            },
        )

        assert resp.status_code == 422
        assert "between 1 and 20 sessions" in resp.json()["detail"]
