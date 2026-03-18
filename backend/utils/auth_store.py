"""Azure Cosmos DB-backed persistence for user credentials.

Replaces the previous JSON file-backed implementation. All public function
signatures are preserved so callers in main.py require no changes.
"""

import logging
from typing import Any, Dict, Optional

import bcrypt

logger = logging.getLogger(__name__)

# Module-level Cosmos DB client. Initialised by load() at FastAPI startup.
_cosmos: Optional[Any] = None  # CosmosUserStore


def load() -> None:
    """Initialise the Cosmos DB connection. Called once at FastAPI startup."""
    global _cosmos
    from base.cosmos_client import CosmosUserStore
    try:
        _cosmos = CosmosUserStore.from_env()
    except ValueError as exc:
        logger.warning("Cosmos DB not configured for auth_store: %s. Auth unavailable.", exc)
        _cosmos = None


def _get_cosmos():
    """Return the Cosmos DB client, raising RuntimeError if not initialised."""
    if _cosmos is None:
        raise RuntimeError(
            "Cosmos DB client not initialised. "
            "Ensure AZURE_COSMOS_CONNECTION_STRING is set and auth_store.load() was called."
        )
    return _cosmos


def create_user(username: str, password: str) -> Dict[str, Any]:
    """Hash password with bcrypt and store. Raises ValueError if user already exists."""
    db = _get_cosmos()
    if db.get("users", username, username) is not None:
        raise ValueError("User already exists")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = {
        "id": username,
        "username": username,
        "password_hash": hashed.decode("utf-8"),
    }
    db.upsert("users", user)
    return {"username": username, "password_hash": user["password_hash"]}


def verify_password(username: str, password: str) -> bool:
    """Check *password* against the stored bcrypt hash for *username*."""
    item = _get_cosmos().get("users", username, username)
    if not item:
        return False
    return bcrypt.checkpw(
        password.encode("utf-8"),
        item["password_hash"].encode("utf-8"),
    )


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Return the user record for *username*, or None if not found."""
    item = _get_cosmos().get("users", username, username)
    if not item:
        return None
    return {"username": item["username"], "password_hash": item["password_hash"]}


def delete_user(username: str) -> bool:
    """Delete the user record. Returns True if the user existed, False otherwise."""
    return _get_cosmos().delete("users", username, username)
