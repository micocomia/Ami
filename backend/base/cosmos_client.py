"""Azure Cosmos DB NoSQL API client wrapper for Ami user data storage.

Follows the same pattern as blob_storage.py:
- Connection string from environment variable
- Lazy container initialization via _container() helper
- Thin wrapper; all Cosmos-specific imports are confined to this file
- from_env() static factory for clean initialization
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cosmos DB system metadata fields returned on every read; stripped before returning to callers.
_COSMOS_SYSTEM_FIELDS = {"_rid", "_self", "_etag", "_attachments", "_ts"}

# Partition key path per container name.
_PARTITION_KEYS: Dict[str, str] = {
    "users": "/username",
    "goals": "/user_id",
    "profiles": "/user_id",
    "profile_snapshots": "/user_id",
    "learning_content": "/user_id",
    "session_activity": "/user_id",
    "mastery_history": "/user_id",
    "events": "/user_id",
}


def strip_cosmos_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """Remove Cosmos DB system metadata fields from a returned item dict."""
    return {k: v for k, v in item.items() if k not in _COSMOS_SYSTEM_FIELDS}


class CosmosUserStore:
    """Thin wrapper around the Azure Cosmos DB NoSQL API for Ami's user data.

    All eight user-data containers are managed here. Containers are created
    automatically on first use via create_container_if_not_exists, so no manual
    Azure portal setup is required beyond creating the Cosmos DB account.
    """

    def __init__(self, connection_string: str, database_name: str = "ami-userdata"):
        from azure.cosmos import CosmosClient, PartitionKey
        self._client = CosmosClient.from_connection_string(connection_string)
        self._db = self._client.create_database_if_not_exists(
            id=database_name,
            offer_throughput=1000,
        )
        self._containers: Dict[str, Any] = {}
        self._PartitionKey = PartitionKey

    def _container(self, name: str) -> Any:
        """Return a lazily-created container proxy for *name*."""
        if name not in self._containers:
            pk_path = _PARTITION_KEYS[name]
            self._containers[name] = self._db.create_container_if_not_exists(
                id=name,
                partition_key=self._PartitionKey(path=pk_path),
            )
        return self._containers[name]

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def upsert(self, container: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or replace an item. Item must contain 'id' and the partition key field."""
        return self._container(container).upsert_item(item)

    def get(self, container: str, item_id: str, partition_key_value: str) -> Optional[Dict[str, Any]]:
        """Read a single item by id. Returns None if not found."""
        from azure.cosmos import exceptions as CosmosExceptions
        try:
            return self._container(container).read_item(
                item=item_id, partition_key=partition_key_value
            )
        except CosmosExceptions.CosmosResourceNotFoundError:
            return None

    def delete(self, container: str, item_id: str, partition_key_value: str) -> bool:
        """Delete an item. Returns True if deleted, False if not found."""
        from azure.cosmos import exceptions as CosmosExceptions
        try:
            self._container(container).delete_item(
                item=item_id, partition_key=partition_key_value
            )
            return True
        except CosmosExceptions.CosmosResourceNotFoundError:
            return False

    def query(
        self,
        container: str,
        query: str,
        parameters: List[Dict[str, Any]],
        partition_key_value: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a parameterised SQL query.

        If *partition_key_value* is given the query is scoped to that logical
        partition (efficient single-partition read). Otherwise a cross-partition
        fan-out query is performed.
        """
        kwargs: Dict[str, Any] = {
            "query": query,
            "parameters": parameters,
            "enable_cross_partition_query": partition_key_value is None,
        }
        if partition_key_value is not None:
            kwargs["partition_key"] = partition_key_value
        return list(self._container(container).query_items(**kwargs))

    def patch(
        self,
        container: str,
        item_id: str,
        partition_key_value: str,
        patch_operations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply partial-update operations to an existing item.

        Each operation is a dict: {"op": "set", "path": "/field_name", "value": v}.
        Requires azure-cosmos >= 4.3.0.
        """
        return self._container(container).patch_item(
            item=item_id,
            partition_key=partition_key_value,
            patch_operations=patch_operations,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Ping the Cosmos DB service. Used at startup to verify connectivity."""
        try:
            list(self._client.list_databases())
            return True
        except Exception as exc:
            logger.warning("Cosmos DB connection check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_env(database_name: str = "ami-userdata") -> "CosmosUserStore":
        """Create a CosmosUserStore from the AZURE_COSMOS_CONNECTION_STRING env var."""
        conn_str = os.environ.get("AZURE_COSMOS_CONNECTION_STRING", "")
        if not conn_str:
            raise ValueError(
                "AZURE_COSMOS_CONNECTION_STRING is not set. "
                "Add it to backend/.env to enable Cosmos DB user storage."
            )
        return CosmosUserStore(conn_str, database_name=database_name)
