"""Authentication bootstrap for protected Beta eval endpoints."""

from __future__ import annotations

import httpx

from evals.Beta.config import EVAL_PASSWORD, EVAL_USERNAME


def bootstrap_auth_headers(
    base_url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, str]:
    username = username or EVAL_USERNAME
    password = password or EVAL_PASSWORD
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)

    def _raise_for_unexpected(response: httpx.Response, action: str) -> None:
        if response.status_code < 400:
            return
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"{action} failed with {response.status_code}: {detail}")

    try:
        register_resp = client.post(
            f"{base_url}/auth/register",
            json={"username": username, "password": password},
        )
        if register_resp.status_code == 409:
            auth_resp = client.post(
                f"{base_url}/auth/login",
                json={"username": username, "password": password},
            )
            _raise_for_unexpected(auth_resp, "auth login")
        else:
            _raise_for_unexpected(register_resp, "auth register")
            auth_resp = register_resp

        try:
            token = auth_resp.json()["token"]
        except Exception as exc:
            raise RuntimeError(f"auth bootstrap did not return a token: {exc}") from exc
        return {"Authorization": f"Bearer {token}"}
    finally:
        if owns_client:
            client.close()
