import uuid

from app.config.settings import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_ready_reports_honest_pre_infrastructure_state() -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert set(body["data"].keys()) == {"status", "inference", "database"}
    # Default test env: sqlite works, no llama-server is running on :8080.
    assert body["data"]["status"] == "not_ready"
    assert body["data"]["inference"] == "unavailable"
    assert body["data"]["database"] == "available"
    assert response.headers["x-request-id"] == body["request_id"]


def test_ready_reports_stub_runtime_available(monkeypatch) -> None:
    monkeypatch.setenv("RUACH_MODEL_RUNTIME", "stub")
    get_settings.cache_clear()
    try:
        response = client.get("/api/v1/ready")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data == {
            "status": "ready",
            "inference": "available",
            "database": "available",
        }
    finally:
        get_settings.cache_clear()


def test_system_reports_only_allowed_fields() -> None:
    response = client.get("/api/v1/system")
    assert response.status_code == 200
    body = response.json()
    assert set(body["data"].keys()) == {
        "ruach_version",
        "api_version",
        "runtime_status",
        "inference",
        "database",
        "tools",
    }
    assert body["data"]["tools"] == "restricted"
    assert body["data"]["ruach_version"]
    assert body["data"]["api_version"] == "v1"
    assert body["data"]["runtime_status"] == "running"
    assert uuid.UUID(body["request_id"])
