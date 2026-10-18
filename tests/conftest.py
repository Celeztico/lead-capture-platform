import os

import pytest
from fastapi.testclient import TestClient

# Load test environment before importing app
os.environ.setdefault("ENV_FILE", ".env.test")

from app.core.database import engine
from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Drop pooled connections between tests.

    asyncpg connections are bound to the event loop that created them, and
    pytest-asyncio runs each test in a fresh loop. Without this, a connection
    pooled by one test would be reused by the next and fail with
    'attached to a different loop'.
    """
    yield
    await engine.dispose()
