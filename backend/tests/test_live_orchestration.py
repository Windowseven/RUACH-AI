"""Live real-model orchestration proof (Priority 2).

These tests run the REAL Qwen model through the FULL application stack:
API -> chat_service -> orchestrator -> InferencePort -> llama-server ->
parser -> policy engine -> approval flow -> persistence.

They are skipped unless RUACH_LIVE_MODEL=1 and a llama-server is
reachable at RUACH_MODEL_SERVER_URL. They are intentionally slow and
are not part of the default unit gate.
"""

import os

import pytest
from app.api.dependencies import (
    get_approval_index,
    get_inference,
    get_session,
    get_tool_engine,
)
from app.application.orchestrator import ApprovalIndex
from app.application.tools.approvals import InMemoryApprovalStore
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.config.settings import get_settings
from app.infrastructure.db import get_engine
from app.infrastructure.inference_llamacpp import LlamaCppAdapter
from app.infrastructure.models import Base
from app.main import app
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("RUACH_LIVE_MODEL") != "1",
        reason="live real-model proof; set RUACH_LIVE_MODEL=1 with llama-server up",
    )
]


@pytest.fixture(scope="module")
def live_client(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("live_ws")
    settings = get_settings()
    adapter = LlamaCppAdapter(
        base_url=settings.model_server_url,
        model_name=settings.model_name,
        timeout_seconds=300.0,
        max_tokens=384,
        temperature=0.2,
        model_path=settings.model_path or None,
    )
    tool_engine = ToolEngine(
        WorkspaceBoundary(workspace),
        InMemoryApprovalStore(ttl_seconds=900.0),
        AuditLog(tmp_path_factory.mktemp("live_audit") / "audit.jsonl"),
    )

    db_engine = get_engine(f"sqlite:///{tmp_path_factory.mktemp('live_db') / 'live.db'}")
    Base.metadata.create_all(db_engine)

    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    def override_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_inference] = lambda: adapter
    app.dependency_overrides[get_tool_engine] = lambda: tool_engine
    approval_index = ApprovalIndex()
    app.dependency_overrides[get_approval_index] = lambda: approval_index
    app.dependency_overrides[get_session] = override_session
    yield TestClient(app), workspace
    app.dependency_overrides.clear()


def test_real_model_reads_file_through_full_stack(live_client) -> None:
    client, workspace = live_client
    (workspace / "notes.txt").write_text("evidence: local loop works", encoding="utf-8")
    response = client.post("/api/v1/chat", json={"message": "read notes.txt"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tool"] is not None, f"no tool activity: {data}"
    assert data["tool"]["state"] == "COMPLETED"
    assert data["tool"]["capability"] == "filesystem.read"
    detail = client.get(f"/api/v1/conversations/{data['conversation_id']}")
    roles = [m["role"] for m in detail.json()["data"]["messages"]]
    assert roles == ["user", "tool", "assistant"], roles


def test_real_model_delete_requires_human_approval(live_client) -> None:
    client, workspace = live_client
    target = workspace / "secret.txt"
    target.write_text("classified", encoding="utf-8")

    first = client.post("/api/v1/chat", json={"message": "delete secret.txt"})
    data = first.json()["data"]
    pending = data.get("pending_approval")
    assert pending is not None, f"expected approval flow, got: {data}"
    assert data["tool"]["state"] == "AWAITING_APPROVAL"
    assert target.exists(), "nothing may execute before approval"

    approved = client.post(
        f"/api/v1/chat/approvals/{pending['approval_id']}/approve",
        json={"approved": True},
    )
    body = approved.json()["data"]
    assert body["tool"]["state"] == "COMPLETED", body
    assert not target.exists(), "approval must result in execution"


def test_real_model_plain_chat_stays_plain(live_client) -> None:
    client, _workspace = live_client
    response = client.post(
        "/api/v1/chat", json={"message": "Answer with one word: what color is grass?"}
    )
    data = response.json()["data"]
    assert data["tool"] is None or data["tool"]["state"] != "AWAITING_APPROVAL"
    assert data["content"].strip()


def test_real_model_multi_turn_name_recall(live_client) -> None:
    """P3 DoD: multi-turn context reaches the REAL model through ContextBuilder."""
    client, _workspace = live_client
    first = client.post(
        "/api/v1/chat",
        json={"message": "My name is Alice. Remember it and just say ok."},
    ).json()["data"]
    cid = first["conversation_id"]

    second = client.post(
        "/api/v1/chat",
        json={"message": "What is my name? Answer with the name only.", "conversation_id": cid},
    ).json()["data"]
    assert "alice" in second["content"].lower(), second["content"]


def test_real_model_coreference_read(live_client) -> None:
    """P3 DoD: a later turn resolves 'the project file' via stored context.

    Behavioral assertion (not choreography): whichever turn performs it,
    the conversation must contain a COMPLETED filesystem.read whose path
    equals the filename given in an EARLIER message, with the file result
    persisted into the conversation record.
    """
    import json as _json

    client, workspace = live_client
    (workspace / "haiku.txt").write_text("first line here", encoding="utf-8")
    first = client.post(
        "/api/v1/chat",
        json={"message": "The project file is haiku.txt."},
    ).json()["data"]
    cid = first["conversation_id"]

    client.post(
        "/api/v1/chat",
        json={"message": "Read the project file.", "conversation_id": cid},
    )

    detail = client.get(f"/api/v1/conversations/{cid}").json()["data"]
    tool_events = [
        _json.loads(m["content"]) for m in detail["messages"] if m["role"] == "tool"
    ]
    assert any(
        event.get("capability") == "filesystem.read"
        and event.get("state") == "COMPLETED"
        and event.get("arguments", {}).get("path") == "haiku.txt"
        for event in tool_events
    ), tool_events
    assert any(
        "first line here" in event.get("result", "") for event in tool_events
    ), "file result must participate in conversation context"
