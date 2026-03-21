"""Tests for bias audit log persistence and the /bias-audit-history endpoint.

Run from backend/:
    python -m pytest tests/test_bias_audit_persistence.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from typing import Any, Dict, List, Optional
from utils import store


# ---------------------------------------------------------------------------
# FakeCosmosUserStore — in-memory implementation for tests
# ---------------------------------------------------------------------------

class FakeCosmosUserStore:
    """In-memory dict-backed fake that implements the CosmosUserStore interface."""

    def __init__(self):
        self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _cdata(self, container: str) -> Dict[str, Dict[str, Any]]:
        return self._data.setdefault(container, {})

    def upsert(self, container: str, item: Dict[str, Any]) -> Dict[str, Any]:
        self._cdata(container)[item["id"]] = dict(item)
        return dict(item)

    def get(self, container: str, item_id: str, partition_key_value: str) -> Optional[Dict[str, Any]]:
        item = self._cdata(container).get(item_id)
        return dict(item) if item is not None else None

    def delete(self, container: str, item_id: str, partition_key_value: str) -> bool:
        return self._cdata(container).pop(item_id, None) is not None

    def query(
        self,
        container: str,
        query: str,
        parameters: List[Dict[str, Any]],
        partition_key_value: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        uid = next((p["value"] for p in parameters if p["name"] == "@uid"), None)
        items = list(self._cdata(container).values())
        if uid is not None:
            items = [
                i for i in items
                if i.get("user_id") == uid or i.get("username") == uid
            ]
        if "c.is_deleted = false" in query:
            items = [i for i in items if not i.get("is_deleted", False)]
        return [dict(i) for i in items]

    def patch(
        self,
        container: str,
        item_id: str,
        partition_key_value: str,
        patch_operations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        doc = dict(self._cdata(container).get(item_id, {}))
        for op in patch_operations:
            if op.get("op") == "set":
                field = op["path"].lstrip("/")
                doc[field] = op["value"]
        self._cdata(container)[item_id] = doc
        return dict(doc)

    def check_connection(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Point store module at a temp directory for JSON stores and use a fake Cosmos client."""
    data_dir = tmp_path / "store_data"
    data_dir.mkdir()
    monkeypatch.setattr(store, "_DATA_DIR", data_dir)
    # Patch JSON-backed stores to temp dir
    monkeypatch.setattr(store, "_PROFILES_PATH", data_dir / "profiles.json")
    monkeypatch.setattr(store, "_EVENTS_PATH", data_dir / "events.json")
    monkeypatch.setattr(store, "_GOALS_PATH", data_dir / "goals.json")
    monkeypatch.setattr(store, "_LEARNING_CONTENT_PATH", data_dir / "learning_content.json")
    monkeypatch.setattr(store, "_SESSION_ACTIVITY_PATH", data_dir / "session_activity.json")
    monkeypatch.setattr(store, "_MASTERY_HISTORY_PATH", data_dir / "mastery_history.json")
    monkeypatch.setattr(store, "_PROFILE_SNAPSHOTS_PATH", data_dir / "profile_snapshots.json")
    monkeypatch.setattr(store, "_profiles", {})
    monkeypatch.setattr(store, "_events", {})
    monkeypatch.setattr(store, "_goals", {})
    monkeypatch.setattr(store, "_learning_content_cache", {})
    monkeypatch.setattr(store, "_session_activity", {})
    monkeypatch.setattr(store, "_mastery_history", {})
    monkeypatch.setattr(store, "_profile_snapshots", {})
    # Use a fake Cosmos client for bias audit log
    monkeypatch.setattr(store, "_cosmos", FakeCosmosUserStore())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit_result(overall_risk="low", flags=None):
    """Build a minimal audit result dict."""
    return {
        "overall_risk": overall_risk,
        "flags": flags or [],
        "audited_items": 5,
    }


# ---------------------------------------------------------------------------
# Store-level tests
# ---------------------------------------------------------------------------

class TestAppendBiasAuditLog:
    def test_basic_append_and_retrieve(self):
        result = _make_audit_result("medium", [
            {"category": "gender", "severity": "medium"},
        ])
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)

        entries = store.get_bias_audit_log("alice")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["audit_type"] == "skill_gap_bias"
        assert entry["overall_risk"] == "medium"
        assert entry["flagged_count"] == 1
        assert entry["audited_count"] == 5
        assert entry["goal_id"] == 0
        assert len(entry["flags_summary"]) == 1
        assert entry["flags_summary"][0]["category"] == "gender"
        assert "timestamp" in entry

    def test_200_entry_cap(self):
        result = _make_audit_result()
        for i in range(210):
            store.append_bias_audit_log("alice", 0, "content_bias", result)

        entries = store.get_bias_audit_log("alice")
        assert len(entries) == 200

    def test_filter_by_goal_id(self):
        result = _make_audit_result()
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)
        store.append_bias_audit_log("alice", 1, "content_bias", result)
        store.append_bias_audit_log("alice", 0, "chatbot_bias", result)

        assert len(store.get_bias_audit_log("alice")) == 3
        assert len(store.get_bias_audit_log("alice", goal_id=0)) == 2
        assert len(store.get_bias_audit_log("alice", goal_id=1)) == 1
        assert len(store.get_bias_audit_log("alice", goal_id=99)) == 0

    def test_empty_user_returns_empty(self):
        assert store.get_bias_audit_log("nonexistent") == []

    def test_returns_isolated_data(self):
        result = _make_audit_result("high", [{"category": "age", "severity": "high"}])
        store.append_bias_audit_log("alice", 0, "profile_fairness", result)

        entries1 = store.get_bias_audit_log("alice")
        entries2 = store.get_bias_audit_log("alice")
        assert entries1 == entries2
        entries1[0]["overall_risk"] = "changed"
        assert store.get_bias_audit_log("alice")[0]["overall_risk"] == "high"

    def test_none_goal_id_stored(self):
        result = _make_audit_result()
        store.append_bias_audit_log("alice", None, "chatbot_bias", result)

        entries = store.get_bias_audit_log("alice")
        assert len(entries) == 1
        assert entries[0]["goal_id"] is None

    def test_multiple_users_isolated(self):
        result = _make_audit_result()
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)
        store.append_bias_audit_log("bob", 0, "content_bias", result)

        assert len(store.get_bias_audit_log("alice")) == 1
        assert len(store.get_bias_audit_log("bob")) == 1
        assert store.get_bias_audit_log("alice")[0]["audit_type"] == "skill_gap_bias"
        assert store.get_bias_audit_log("bob")[0]["audit_type"] == "content_bias"

    def test_cosmos_container_stores_data(self):
        """Verify data is stored in the Cosmos bias_audit_log container."""
        result = _make_audit_result("medium")
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)

        # Verify the data is in the Cosmos container via the client
        item = store._cosmos.get("bias_audit_log", "alice", "alice")
        assert item is not None
        assert len(item["entries"]) == 1

    def test_flags_summary_capped_at_20(self):
        flags = [{"category": f"cat_{i}", "severity": "low"} for i in range(30)]
        result = _make_audit_result("high", flags)
        store.append_bias_audit_log("alice", 0, "content_bias", result)

        entry = store.get_bias_audit_log("alice")[0]
        assert entry["flagged_count"] == 30
        assert len(entry["flags_summary"]) == 20

    def test_delete_all_user_data_clears_log(self):
        result = _make_audit_result()
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)
        assert len(store.get_bias_audit_log("alice")) == 1

        store.delete_all_user_data("alice")
        assert store.get_bias_audit_log("alice") == []


# ---------------------------------------------------------------------------
# Endpoint tests — import app lazily to handle env issues
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    try:
        from main import app
        from fastapi.testclient import TestClient
        from utils.auth_jwt import get_current_user
        app.dependency_overrides[get_current_user] = lambda: "alice"
        c = TestClient(app)
        yield c
        app.dependency_overrides.pop(get_current_user, None)
    except Exception:
        pytest.skip("Cannot import main app (chromadb or other env issue)")


class TestBiasAuditHistoryEndpoint:
    def test_returns_entries_and_summary(self, client):
        result = _make_audit_result("medium", [
            {"category": "gender", "severity": "medium"},
            {"category": "cultural", "severity": "low"},
        ])
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", result)
        store.append_bias_audit_log("alice", 0, "content_bias", _make_audit_result("low"))

        resp = client.get("/v1/bias-audit-history/alice")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]) == 2
        summary = body["summary"]
        assert summary["total_audits"] == 2
        assert summary["total_flags"] == 2
        assert summary["current_risk"] == "low"
        assert summary["risk_distribution"]["medium"] == 1
        assert summary["risk_distribution"]["low"] == 1
        assert "gender" in summary["category_counts"]

    def test_filter_by_goal_id(self, client):
        store.append_bias_audit_log("alice", 0, "skill_gap_bias", _make_audit_result())
        store.append_bias_audit_log("alice", 1, "content_bias", _make_audit_result())

        resp = client.get("/v1/bias-audit-history/alice?goal_id=1")
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 1

    def test_empty_history(self, client):
        resp = client.get("/v1/bias-audit-history/alice")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entries"] == []
        assert body["summary"]["total_audits"] == 0
        assert body["summary"]["current_risk"] == "low"

    def test_forbidden_for_other_user(self, client):
        resp = client.get("/v1/bias-audit-history/bob")
        assert resp.status_code == 403
