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


def _truncate_test_tables(sync_conn):
    from sqlalchemy import text

    rows = sync_conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    tables = [row[0] for row in rows]
    if tables:
        names = ", ".join(f'"{t}"' for t in tables)
        sync_conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
async def _clean_test_database():
    """Start each test from an empty database.

    Integration fixtures reuse fixed emails (demo@example.com, ...), so leftover
    rows from previous runs change workspace resolution and list results. Only
    databases whose name ends in '_test' are truncated - development data is
    never touched.
    """
    if (engine.url.database or "").endswith("_test"):
        async with engine.begin() as conn:
            await conn.run_sync(_truncate_test_tables)
        # Close the fixture's loop-bound connection so the test checks out a
        # fresh one created on its own event loop.
        await engine.dispose()
    yield


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
