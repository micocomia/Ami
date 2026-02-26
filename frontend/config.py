import os
from urllib.parse import urlparse, urlunparse


def _normalize_endpoint(endpoint: str, fallback: str) -> str:
    value = (endpoint or "").strip() or fallback
    return value if value.endswith("/") else f"{value}/"


def _derive_public_endpoint(internal_endpoint: str) -> str:
    parsed = urlparse(internal_endpoint)
    if parsed.hostname == "host.docker.internal":
        port = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or "/"
        rebuilt = urlunparse((parsed.scheme or "http", f"localhost{port}", path, "", "", ""))
        return _normalize_endpoint(rebuilt, "http://localhost:8000/")
    return _normalize_endpoint(internal_endpoint, "http://127.0.0.1:8000/")


backend_endpoint = _normalize_endpoint(os.getenv("BACKEND_ENDPOINT", "http://127.0.0.1:8000/"), "http://127.0.0.1:8000/")
backend_public_endpoint = _normalize_endpoint(
    os.getenv("BACKEND_PUBLIC_ENDPOINT", _derive_public_endpoint(backend_endpoint)),
    _derive_public_endpoint(backend_endpoint),
)
use_mock_data = False
use_search = True
