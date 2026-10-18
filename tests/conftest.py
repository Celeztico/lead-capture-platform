import os

import pytest
from fastapi.testclient import TestClient

# Load test environment before importing app
os.environ.setdefault("ENV_FILE", ".env.test")

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)
