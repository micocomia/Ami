"""JWT token creation and verification."""

import os
from datetime import datetime, timedelta
from typing import Optional

import jwt
from jwt.utils import base64url_decode, base64url_encode

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"


def create_token(username: str) -> str:
    """Create a JWT with 24h expiry and sub=username."""
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    """Decode JWT and return the username, or None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signature = parts[2]
        canonical_signature = base64url_encode(base64url_decode(signature.encode("utf-8"))).decode("utf-8").rstrip("=")
        if signature != canonical_signature:
            return None
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
    except Exception:
        return None
