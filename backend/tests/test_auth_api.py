"""Tests for authentication API endpoints (register, login, /auth/me, delete account).

These test the full HTTP request/response cycle via FastAPI's TestClient,
covering flows 1 (login/logout) and 3 (account deletion).

Run from the repo root:
    python -m pytest backend/tests/test_auth_api.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from utils import store, auth_store, auth_jwt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point store module at a temp directory and reset in-memory state."""
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_USER_STATES_PATH", data_dir / "user_states.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_user_states", {})


@pytest.fixture(autouse=True)
def _isolate_auth_store(tmp_path, monkeypatch):
    """Point auth_store module at a temp directory and reset in-memory state."""
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
# Helper
# ---------------------------------------------------------------------------

def _register(client, username="testuser", password="secret123"):
    """Register a user and return (status_code, response_json)."""
    resp = client.post("/auth/register", json={"username": username, "password": password})
    return resp.status_code, resp.json()


def _login(client, username="testuser", password="secret123"):
    """Login a user and return (status_code, response_json)."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.status_code, resp.json()


# ===================================================================
# POST /auth/register
# ===================================================================

class TestRegisterEndpoint:
    def test_register_success(self, client):
        status, data = _register(client, "alice", "password123")
        assert status == 200
        assert "token" in data
        assert data["username"] == "alice"

    def test_register_returns_valid_jwt(self, client):
        _, data = _register(client, "alice", "password123")
        username = auth_jwt.verify_token(data["token"])
        assert username == "alice"

    def test_register_short_username_rejected(self, client):
        resp = client.post("/auth/register", json={"username": "ab", "password": "password123"})
        assert resp.status_code == 400
        assert "3 characters" in resp.json()["detail"]

    def test_register_short_password_rejected(self, client):
        resp = client.post("/auth/register", json={"username": "alice", "password": "12345"})
        assert resp.status_code == 400
        assert "6 characters" in resp.json()["detail"]

    def test_register_duplicate_username_rejected(self, client):
        _register(client, "alice", "password123")
        status, data = _register(client, "alice", "otherpassword")
        assert status == 409
        assert "already exists" in data["detail"]

    def test_register_creates_user_in_store(self, client):
        _register(client, "alice", "password123")
        assert auth_store.get_user("alice") is not None
        assert auth_store.verify_password("alice", "password123") is True


# ===================================================================
# POST /auth/login
# ===================================================================

class TestLoginEndpoint:
    def test_login_success(self, client):
        _register(client, "alice", "password123")
        status, data = _login(client, "alice", "password123")
        assert status == 200
        assert "token" in data
        assert data["username"] == "alice"

    def test_login_returns_valid_jwt(self, client):
        _register(client, "alice", "password123")
        _, data = _login(client, "alice", "password123")
        username = auth_jwt.verify_token(data["token"])
        assert username == "alice"

    def test_login_wrong_password(self, client):
        _register(client, "alice", "password123")
        status, data = _login(client, "alice", "wrongpassword")
        assert status == 401
        assert "Invalid" in data["detail"]

    def test_login_nonexistent_user(self, client):
        status, data = _login(client, "nobody", "password123")
        assert status == 401

    def test_login_after_register_same_session(self, client):
        """Register then immediately login with the same credentials."""
        _register(client, "alice", "password123")
        status, data = _login(client, "alice", "password123")
        assert status == 200
        assert data["username"] == "alice"


# ===================================================================
# GET /auth/me  (token verification)
# ===================================================================

class TestAuthMeEndpoint:
    def test_auth_me_with_valid_token(self, client):
        _, reg_data = _register(client, "alice", "password123")
        token = reg_data["token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_auth_me_with_invalid_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_auth_me_with_no_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_auth_me_after_login(self, client):
        _register(client, "alice", "password123")
        _, login_data = _login(client, "alice", "password123")
        token = login_data["token"]
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"


# ===================================================================
# DELETE /auth/user  (account deletion)
# ===================================================================

class TestDeleteAccountEndpoint:
    def test_delete_account_success(self, client):
        _, reg_data = _register(client, "alice", "password123")
        token = reg_data["token"]
        resp = client.delete("/auth/user", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_delete_account_removes_user_from_auth_store(self, client):
        _, reg_data = _register(client, "alice", "password123")
        token = reg_data["token"]
        client.delete("/auth/user", headers={"Authorization": f"Bearer {token}"})
        assert auth_store.get_user("alice") is None

    def test_delete_account_removes_all_user_data(self, client):
        _, reg_data = _register(client, "alice", "password123")
        token = reg_data["token"]

        # Create some user data (profiles, events, user state)
        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("alice", 1, {"goal": "Rust"})
        store.append_event("alice", {"type": "page_view"})
        store.put_user_state("alice", {"goals": []})

        client.delete("/auth/user", headers={"Authorization": f"Bearer {token}"})

        assert store.get_profile("alice", 0) is None
        assert store.get_profile("alice", 1) is None
        assert store.get_events("alice") == []
        assert store.get_user_state("alice") is None

    def test_delete_account_preserves_other_users_data(self, client):
        _register(client, "alice", "password123")
        _register(client, "bob", "password456")
        _, alice_data = _login(client, "alice", "password123")

        store.upsert_profile("alice", 0, {"goal": "Python"})
        store.upsert_profile("bob", 0, {"goal": "Go"})
        store.put_user_state("bob", {"theme": "dark"})

        client.delete("/auth/user", headers={"Authorization": f"Bearer {alice_data['token']}"})

        # Bob's data should be untouched
        assert store.get_profile("bob", 0) == {"goal": "Go"}
        assert store.get_user_state("bob") == {"theme": "dark"}
        assert auth_store.get_user("bob") is not None

    def test_delete_account_with_invalid_token(self, client):
        resp = client.delete("/auth/user", headers={"Authorization": "Bearer bad.token"})
        assert resp.status_code == 401

    def test_delete_account_with_no_token(self, client):
        resp = client.delete("/auth/user")
        assert resp.status_code == 401

    def test_login_fails_after_account_deletion(self, client):
        _, reg_data = _register(client, "alice", "password123")
        token = reg_data["token"]
        client.delete("/auth/user", headers={"Authorization": f"Bearer {token}"})

        # Login should now fail
        status, _ = _login(client, "alice", "password123")
        assert status == 401


# ===================================================================
# Full lifecycle: register -> login -> verify -> delete -> verify gone
# ===================================================================

class TestFullAuthLifecycle:
    def test_register_login_verify_delete(self, client):
        """End-to-end: register, login, verify token, delete account."""
        # 1. Register
        status, reg_data = _register(client, "alice", "password123")
        assert status == 200
        token = reg_data["token"]

        # 2. Login
        status, login_data = _login(client, "alice", "password123")
        assert status == 200
        login_token = login_data["token"]

        # 3. Verify via /auth/me
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {login_token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

        # 4. Create some user data
        store.upsert_profile("alice", 0, {"goal": "Learn Python"})
        store.put_user_state("alice", {"if_complete_onboarding": True})

        # 5. Delete account
        resp = client.delete("/auth/user", headers={"Authorization": f"Bearer {login_token}"})
        assert resp.status_code == 200

        # 6. Verify account is gone
        assert auth_store.get_user("alice") is None
        assert store.get_profile("alice", 0) is None
        assert store.get_user_state("alice") is None

        # 7. Login should fail
        status, _ = _login(client, "alice", "password123")
        assert status == 401
