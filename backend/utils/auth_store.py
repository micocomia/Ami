"""JSON file-backed persistence for user credentials."""

import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import bcrypt

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "users"
_USERS_PATH = _DATA_DIR / "users.json"

_lock = threading.Lock()
_users: Dict[str, Dict[str, Any]] = {}


def load():
    """Read persisted user data from disk into memory. Call once at startup."""
    global _users
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _USERS_PATH.exists():
        try:
            _users = json.loads(_USERS_PATH.read_text(encoding="utf-8"))
        except Exception:
            _users = {}


def _flush():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USERS_PATH.write_text(
        json.dumps(_users, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def create_user(username: str, password: str) -> Dict[str, Any]:
    """Hash password with bcrypt and store. Raises ValueError if user exists."""
    with _lock:
        if username in _users:
            raise ValueError("User already exists")
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        _users[username] = {"username": username, "password_hash": hashed.decode("utf-8")}
        _flush()
        return _users[username]


def verify_password(username: str, password: str) -> bool:
    """Check password against stored bcrypt hash."""
    user = _users.get(username)
    if not user:
        return False
    return bcrypt.checkpw(
        password.encode("utf-8"), user["password_hash"].encode("utf-8")
    )


def get_user(username: str) -> Optional[Dict[str, Any]]:
    return _users.get(username)


def delete_user(username: str) -> bool:
    with _lock:
        removed = _users.pop(username, None)
        _flush()
        return removed is not None
