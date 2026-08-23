import uuid

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _submit(capability: str, **arguments):
    return client.post(
        "/api/v1/tools/requests",
        json={"tool": "filesystem", "capability": capability, "arguments": arguments},
    )


def test_registry_lists_capabilities_with_risk_and_mode() -> None:
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "restricted"
    caps = {c["capability"]: c for c in data["tools"]}
    assert caps["filesystem.read"]["risk_level"] == 0
    assert caps["filesystem.delete"]["approval_required"] is True


def test_read_inside_workspace_roundtrips_over_http(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hi.txt").write_text("over http", encoding="utf-8")
    from app.api import dependencies

    dependencies._engine = dependencies.ToolEngine(
        dependencies.WorkspaceBoundary(ws),
        dependencies.InMemoryApprovalStore(),
        dependencies.AuditLog(tmp_path / "audit.jsonl"),
    )
    try:
        response = _submit("filesystem.read", path="hi.txt")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["state"] == "COMPLETED"
        assert data["output"] == "over http"
        assert response.json()["request_id"]
    finally:
        dependencies._engine = None


def test_traversal_is_denied_not_an_http_error(tmp_path) -> None:
    from app.api import dependencies

    dependencies._engine = dependencies.ToolEngine(
        dependencies.WorkspaceBoundary(tmp_path / "ws2"),
        dependencies.InMemoryApprovalStore(),
        dependencies.AuditLog(tmp_path / "audit.jsonl"),
    )
    try:
        response = _submit("filesystem.read", path="../../etc/passwd")
        assert response.status_code == 200
        assert response.json()["data"]["state"] == "DENIED"
    finally:
        dependencies._engine = None


def test_delete_requires_then_honors_approval_over_http(tmp_path) -> None:
    ws = tmp_path / "ws3"
    ws.mkdir()
    target = ws / "gone.txt"
    target.write_text("bye", encoding="utf-8")
    from app.api import dependencies

    dependencies._engine = dependencies.ToolEngine(
        dependencies.WorkspaceBoundary(ws),
        dependencies.InMemoryApprovalStore(),
        dependencies.AuditLog(tmp_path / "audit.jsonl"),
    )
    try:
        pending = _submit("filesystem.delete", path="gone.txt").json()["data"]
        assert pending["state"] == "AWAITING_APPROVAL"
        assert target.exists()

        approved = client.post(
            f"/api/v1/tools/approvals/{pending['approval_id']}/approve"
        )
        assert approved.status_code == 200
        assert approved.json()["data"]["state"] == "COMPLETED"
        assert not target.exists()

        replay = client.post(
            f"/api/v1/tools/approvals/{pending['approval_id']}/approve"
        )
        assert replay.json()["data"]["state"] == "DENIED"

        unknown = client.post(
            f"/api/v1/tools/approvals/{uuid.uuid4().hex}/reject"
        )
        assert unknown.json()["data"]["state"] == "DENIED"
    finally:
        dependencies._engine = None
