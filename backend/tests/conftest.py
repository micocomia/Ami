"""Shared test fixtures for the Ami backend test suite."""
import pytest


@pytest.fixture(autouse=True)
def _bypass_auth():
    """Override get_current_user for all tests to return 'alice'.

    This allows tests to exercise authenticated endpoints without needing
    real JWT tokens. The dependency override is cleaned up after each test.
    """
    from main import app
    from utils.auth_jwt import get_current_user

    app.dependency_overrides[get_current_user] = lambda: "alice"
    yield
    app.dependency_overrides.pop(get_current_user, None)
