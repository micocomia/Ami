"""Shared test fixtures for the Ami backend test suite."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# FakeCosmosUserStore — in-memory implementation of CosmosUserStore interface
# ---------------------------------------------------------------------------

class FakeCosmosUserStore:
    """In-memory dict-backed fake that implements the CosmosUserStore interface.

    Used by all tests to avoid real Cosmos DB connections. Provides the same
    upsert/get/delete/query/patch/check_connection API as CosmosUserStore.
    """

    def __init__(self):
        # container_name -> {item_id: item_dict}
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
# Autouse fixtures applied to all tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_cosmos_stores(monkeypatch):
    """Replace Cosmos DB clients with in-memory fakes for every test.

    Each test gets a fresh instance so state is isolated.
    """
    from utils import store
    fake = FakeCosmosUserStore()
    monkeypatch.setattr(store, "_cosmos", fake)


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Override get_current_user for all tests to return 'alice'.

    This allows tests to exercise authenticated endpoints without needing
    real JWT tokens. The dependency override is cleaned up after each test.
    """
    try:
        from main import app
        from utils.auth_jwt import get_current_user
    except Exception:
        yield
        return

    app.dependency_overrides[get_current_user] = lambda: "alice"
    yield
    app.dependency_overrides.pop(get_current_user, None)
