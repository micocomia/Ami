"""Shared test fixtures for the Ami backend test suite."""
import pytest


@pytest.fixture(autouse=True)
def _bypass_auth(request):
    """Override get_current_user for all tests to return 'alice'.

    This allows tests to exercise authenticated endpoints without needing
    real JWT tokens. The dependency override is cleaned up after each test.

    If the main app cannot be imported (e.g. chromadb/pydantic conflict on
    Python 3.14 or missing native deps), the fixture silently yields so that
    pure unit tests that never touch the FastAPI app still run.
    """
    try:
        from main import app
        from utils.auth_jwt import get_current_user
    except Exception:
        # app unavailable — nothing to override; let pure-logic tests pass.
        yield
        return

    app.dependency_overrides[get_current_user] = lambda: "alice"
    yield
    app.dependency_overrides.pop(get_current_user, None)
