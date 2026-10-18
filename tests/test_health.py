from fastapi.testclient import TestClient


def test_liveness(client: TestClient):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_no_db(client: TestClient):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["database"] == "disconnected"
