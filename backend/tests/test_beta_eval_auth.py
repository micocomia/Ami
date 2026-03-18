import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.Beta.auth import bootstrap_auth_headers


def test_bootstrap_auth_headers_register_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/auth/register"
        return httpx.Response(200, json={"token": "register-token", "username": "beta"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        headers = bootstrap_auth_headers("http://test/v1", client=client, username="beta", password="secret123")

    assert headers == {"Authorization": "Bearer register-token"}


def test_bootstrap_auth_headers_falls_back_to_login_on_conflict():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/register":
            return httpx.Response(409, json={"detail": "Username already exists"})
        assert request.url.path == "/v1/auth/login"
        return httpx.Response(200, json={"token": "login-token", "username": "beta"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        headers = bootstrap_auth_headers("http://test/v1", client=client, username="beta", password="secret123")

    assert headers == {"Authorization": "Bearer login-token"}


def test_bootstrap_auth_headers_raises_on_login_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/register":
            return httpx.Response(409, json={"detail": "Username already exists"})
        return httpx.Response(401, json={"detail": "Invalid username or password"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="auth login failed"):
            bootstrap_auth_headers("http://test/v1", client=client, username="beta", password="secret123")
