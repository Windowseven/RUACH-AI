import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_enveloped_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {"status": "ok"}
    assert response.headers["x-request-id"] == body["request_id"]


def test_request_id_is_generated_when_client_sends_none() -> None:
    response = client.get("/api/v1/health")
    uuid.UUID(response.json()["request_id"])


def test_provided_request_id_is_echoed() -> None:
    sent = "test-rid-42"
    response = client.get("/api/v1/health", headers={"X-Request-ID": sent})
    assert response.headers["x-request-id"] == sent
    assert response.json()["request_id"] == sent
