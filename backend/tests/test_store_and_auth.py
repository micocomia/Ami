"""Tests for store persistence (profiles/events) and auth (registration/login/JWT).

Run from the repo root:
    python -m pytest backend/tests/test_store_and_auth.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import store, auth_store, auth_jwt


# ===================================================================
# store.py – profile persistence
# ===================================================================

class TestProfilePersistence:
    def test_upsert_and_get_profile(self):
        profile = {"learning_goal": "Learn Python", "level": "beginner"}
        store.upsert_profile("alice", 0, profile)

        result = store.get_profile("alice", 0)
        assert result == profile

    def test_get_nonexistent_profile_returns_none(self):
        assert store.get_profile("nobody", 0) is None

    def test_upsert_overwrites_existing(self):
        store.upsert_profile("alice", 0, {"v": 1})
        store.upsert_profile("alice", 0, {"v": 2})
        assert store.get_profile("alice", 0) == {"v": 2}

    def test_multiple_goals_per_user(self):
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})

        assert store.get_profile("alice", 0)["goal"] == "Python"
        assert store.get_profile("alice", 1)["goal"] == "Rust"

    def test_get_all_profiles_for_user(self):
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})
        store.upsert_profile("bob", 0, {"goal": "Go"})

        alice_profiles = store.get_all_profiles_for_user("alice")
        assert len(alice_profiles) == 2
        assert alice_profiles[0]["goal"] == "Python"
        assert alice_profiles[1]["goal"] == "Rust"


# ===================================================================
# store.py – profile snapshot persistence
# ===================================================================

class TestProfileSnapshotPersistence:
    def test_save_and_get_snapshot(self):
        profile = {"v": 1}
        store.save_profile_snapshot("alice", 0, profile)
        assert store.get_profile_snapshot("alice", 0) == {"v": 1}

    def test_get_nonexistent_snapshot_returns_none(self):
        assert store.get_profile_snapshot("nobody", 0) is None

    def test_save_snapshot_does_not_affect_profile(self):
        store.upsert_profile("alice", 0, {"v": "current"})
        store.save_profile_snapshot("alice", 0, {"v": "old"})
        # The live profile is unchanged
        assert store.get_profile("alice", 0) == {"v": "current"}
        # The snapshot is the old value
        assert store.get_profile_snapshot("alice", 0) == {"v": "old"}

    def test_overwrite_snapshot(self):
        store.save_profile_snapshot("alice", 0, {"v": 1})
        store.save_profile_snapshot("alice", 0, {"v": 2})
        assert store.get_profile_snapshot("alice", 0) == {"v": 2}

    def test_delete_snapshot(self):
        store.save_profile_snapshot("alice", 0, {"v": 1})
        store.delete_profile_snapshot("alice", 0)
        assert store.get_profile_snapshot("alice", 0) is None

    def test_delete_nonexistent_snapshot_is_noop(self):
        # Should not raise
        store.delete_profile_snapshot("nobody", 99)


# ===================================================================
# store.py – event persistence
# ===================================================================

class TestEventPersistence:
    def test_append_and_get_events(self):
        store.append_event("alice", {"type": "page_view", "page": "onboarding"})
        events = store.get_events("alice")
        assert len(events) == 1
        assert events[0]["type"] == "page_view"

    def test_get_events_empty_user(self):
        assert store.get_events("nobody") == []

    def test_multiple_events(self):
        store.append_event("alice", {"type": "a"})
        store.append_event("alice", {"type": "b"})
        store.append_event("alice", {"type": "c"})
        events = store.get_events("alice")
        assert len(events) == 3
        assert [e["type"] for e in events] == ["a", "b", "c"]

    def test_events_capped_at_200(self):
        for i in range(210):
            store.append_event("alice", {"i": i})
        events = store.get_events("alice")
        assert len(events) == 200
        # oldest events should be trimmed
        assert events[0]["i"] == 10

    def test_events_isolated_between_users(self):
        store.append_event("alice", {"type": "a"})
        store.append_event("bob", {"type": "b"})
        assert len(store.get_events("alice")) == 1
        assert len(store.get_events("bob")) == 1
        assert store.get_events("alice")[0]["type"] == "a"


# ===================================================================
# auth_store.py – user creation and password verification
# ===================================================================

class TestAuthStore:
    def test_create_user_and_get(self):
        auth_store.create_user("alice", "secret123")
        user = auth_store.get_user("alice")
        assert user is not None
        assert user["username"] == "alice"
        assert "password_hash" in user
        # password should be hashed, not stored in plain text
        assert user["password_hash"] != "secret123"

    def test_verify_correct_password(self):
        auth_store.create_user("alice", "secret123")
        assert auth_store.verify_password("alice", "secret123") is True

    def test_verify_wrong_password(self):
        auth_store.create_user("alice", "secret123")
        assert auth_store.verify_password("alice", "wrongpass") is False

    def test_verify_nonexistent_user(self):
        assert auth_store.verify_password("nobody", "anything") is False

    def test_duplicate_user_raises(self):
        auth_store.create_user("alice", "secret123")
        with pytest.raises(ValueError, match="already exists"):
            auth_store.create_user("alice", "otherpass")

    def test_multiple_users(self):
        auth_store.create_user("alice", "pass1")
        auth_store.create_user("bob", "pass2")

        assert auth_store.verify_password("alice", "pass1") is True
        assert auth_store.verify_password("bob", "pass2") is True
        # cross-check: alice's password doesn't work for bob
        assert auth_store.verify_password("bob", "pass1") is False

    def test_delete_user(self):
        auth_store.create_user("alice", "secret123")
        assert auth_store.delete_user("alice") is True
        assert auth_store.get_user("alice") is None

    def test_delete_user_nonexistent_returns_false(self):
        assert auth_store.delete_user("nobody") is False


# ===================================================================
# store.py – delete_all_user_data
# ===================================================================

class TestDeleteAllUserData:
    def test_delete_all_user_data_removes_profiles(self):
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})
        store.upsert_profile("bob", 0, {"goal": "Go"})

        store.delete_all_user_data("alice")

        assert store.get_profile("alice", 0) is None
        assert store.get_profile("alice", 1) is None
        assert store.get_profile("bob", 0) == {"goal": "Go"}

    def test_delete_all_user_data_removes_events(self):
        store.append_event("alice", {"type": "click"})
        store.append_event("bob", {"type": "scroll"})

        store.delete_all_user_data("alice")

        assert store.get_events("alice") == []
        assert len(store.get_events("bob")) == 1

    def test_delete_all_user_data_removes_goal_content_and_activity(self):
        alice_goal = store.create_goal("alice", {"learning_goal": "Python"})
        bob_goal = store.create_goal("bob", {"learning_goal": "Go"})
        store.upsert_learning_content("alice", alice_goal["id"], 0, {"document": "A", "quizzes": {}})
        store.upsert_learning_content("bob", bob_goal["id"], 0, {"document": "B", "quizzes": {}})
        store.upsert_session_activity("alice", alice_goal["id"], 0, {"start_time": "2026-01-01T00:00:00+00:00"})
        store.upsert_session_activity("bob", bob_goal["id"], 0, {"start_time": "2026-01-01T00:00:00+00:00"})
        store.append_mastery_history("alice", alice_goal["id"], 0.5)
        store.append_mastery_history("bob", bob_goal["id"], 0.25)

        store.delete_all_user_data("alice")

        assert store.get_goal("alice", alice_goal["id"]) is None
        assert store.get_learning_content("alice", alice_goal["id"], 0) is None
        assert store.get_session_activity("alice", alice_goal["id"], 0) is None
        assert store.get_mastery_history("alice", alice_goal["id"]) == []
        assert store.get_goal("bob", bob_goal["id"]) is not None
        assert store.get_learning_content("bob", bob_goal["id"], 0) is not None
        assert store.get_session_activity("bob", bob_goal["id"], 0) is not None
        assert store.get_mastery_history("bob", bob_goal["id"]) != []

    def test_delete_all_user_data_removes_snapshots(self):
        store.save_profile_snapshot("alice", 0, {"v": "snap"})
        store.save_profile_snapshot("alice", 1, {"v": "snap2"})
        store.save_profile_snapshot("bob", 0, {"v": "bob_snap"})

        store.delete_all_user_data("alice")

        assert store.get_profile_snapshot("alice", 0) is None
        assert store.get_profile_snapshot("alice", 1) is None
        # Bob's snapshot is untouched
        assert store.get_profile_snapshot("bob", 0) == {"v": "bob_snap"}


# ===================================================================
# auth_jwt.py – token creation and verification
# ===================================================================

class TestAuthJWT:
    def test_create_and_verify_token(self):
        token = auth_jwt.create_token("alice")
        assert isinstance(token, str)
        assert auth_jwt.verify_token(token) == "alice"

    def test_different_users_get_different_tokens(self):
        t1 = auth_jwt.create_token("alice")
        t2 = auth_jwt.create_token("bob")
        assert t1 != t2
        assert auth_jwt.verify_token(t1) == "alice"
        assert auth_jwt.verify_token(t2) == "bob"

    def test_invalid_token_returns_none(self):
        assert auth_jwt.verify_token("not.a.real.token") is None

    def test_tampered_token_returns_none(self):
        token = auth_jwt.create_token("alice")
        # flip a character in the signature portion
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        assert auth_jwt.verify_token(tampered) is None

    def test_expired_token_returns_none(self, monkeypatch):
        from datetime import datetime, timedelta
        import jwt as pyjwt

        expired_payload = {
            "sub": "alice",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        token = pyjwt.encode(expired_payload, auth_jwt.JWT_SECRET, algorithm=auth_jwt.JWT_ALGORITHM)
        assert auth_jwt.verify_token(token) is None
