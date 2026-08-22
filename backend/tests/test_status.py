import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ready_reports_honest_pre_infrastructure_state() -> None:
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert set(body["data"].keys()) == {"status", "inference", "database"}
    assert body["data"]["status"] == "not_ready"
    assert body["data"]["inference"] == "unavailable"
    assert body["data"]["database"] == "unavailable"
    assert response.headers["x-request-id"] == body["request_id"]


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
    }
    assert body["data"]["ruach_version"]
    assert body["data"]["api_version"] == "v1"
    assert body["data"]["runtime_status"] == "running"
    assert uuid.UUID(body["request_id"])
