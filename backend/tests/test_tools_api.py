import uuid

import pytest
from app.api.dependencies import get_tool_engine
from app.application.tools.approvals import InMemoryApprovalStore
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from fastapi.testclient import TestClient


@pytest.fixture()
def tool_workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    engine = ToolEngine(
        WorkspaceBoundary(ws),
        InMemoryApprovalStore(),
        AuditLog(tmp_path / "audit.jsonl"),
    )
    from app.main import app

    app.dependency_overrides[get_tool_engine] = lambda: engine
    return ws


def _submit(client: TestClient, capability: str, **arguments):
    return client.post(
        "/api/v1/tools/requests",
        json={"tool": "filesystem", "capability": capability, "arguments": arguments},
    )


def test_registry_lists_capabilities_with_risk_and_mode(client) -> None:
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "restricted"
    caps = {c["capability"]: c for c in data["tools"]}
    assert caps["filesystem.read"]["risk_level"] == 0
    assert caps["filesystem.delete"]["approval_required"] is True


def test_read_inside_workspace_roundtrips_over_http(client, tool_workspace) -> None:
    (tool_workspace / "hi.txt").write_text("over http", encoding="utf-8")
    response = _submit(client, "filesystem.read", path="hi.txt")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] == "COMPLETED"
    assert data["output"] == "over http"
    assert response.json()["request_id"]


def test_traversal_is_denied_not_an_http_error(client, tool_workspace) -> None:
    response = _submit(client, "filesystem.read", path="../../etc/passwd")
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "DENIED"


def test_delete_requires_then_honors_approval_over_http(
    client, tool_workspace
) -> None:
    target = tool_workspace / "gone.txt"
    target.write_text("bye", encoding="utf-8")

    pending = _submit(client, "filesystem.delete", path="gone.txt").json()["data"]
    assert pending["state"] == "AWAITING_APPROVAL"
    assert target.exists()

    approved = client.post(f"/api/v1/tools/approvals/{pending['approval_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["data"]["state"] == "COMPLETED"
    assert not target.exists()

    replay = client.post(f"/api/v1/tools/approvals/{pending['approval_id']}/approve")
    assert replay.json()["data"]["state"] == "DENIED"

    unknown = client.post(f"/api/v1/tools/approvals/{uuid.uuid4().hex}/reject")
    assert unknown.json()["data"]["state"] == "DENIED"
