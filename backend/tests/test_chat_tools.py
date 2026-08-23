"""End-to-end orchestration tests: chat -> tool proposal -> policy -> approval.

Uses the stub runtime, which emits protocol-correct tool proposals for a
tiny command grammar. Everything downstream (parsing, engine policy,
approval flow, persistence) is the real production code.
"""



def _history(client, conversation_id):
    return client.get(f"/api/v1/conversations/{conversation_id}").json()["data"][
        "messages"
    ]


def test_plain_message_still_replies_without_tool_metadata(client) -> None:
    response = client.post("/api/v1/chat", json={"message": "hello there"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["content"] == "[stub] You said: hello there"
    assert data["tool"] is None
    assert data["pending_approval"] is None


def test_read_request_completes_and_persists_tool_event(client, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "notes.txt").write_text("the answer is 42", encoding="utf-8")

    response = client.post("/api/v1/chat", json={"message": "read notes.txt"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tool"]["state"] == "COMPLETED"
    assert data["tool"]["capability"] == "filesystem.read"
    assert "action completed" in data["content"].lower()

    messages = _history(client, data["conversation_id"])
    roles = [m["role"] for m in messages]
    assert roles == ["user", "tool", "assistant"]
    tool_event = next(m for m in messages if m["role"] == "tool")
    assert '"state": "COMPLETED"' in tool_event["content"]


def test_delete_request_surfaces_approval_then_approve_executes(
    client, tmp_path
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "secret.txt"
    target.parent.mkdir(exist_ok=True)
    target.write_text("classified", encoding="utf-8")

    first = client.post("/api/v1/chat", json={"message": "delete secret.txt"})
    data = first.json()["data"]
    assert data["pending_approval"] is not None
    assert data["pending_approval"]["capability"] == "filesystem.delete"
    assert target.exists(), "nothing may execute before approval"

    conversation_id = data["conversation_id"]
    approval_id = data["pending_approval"]["approval_id"]

    approved = client.post(
        f"/api/v1/chat/approvals/{approval_id}/approve", json={"approved": True}
    )
    assert approved.status_code == 200
    body = approved.json()["data"]
    assert body["conversation_id"] == conversation_id
    assert body["tool"]["state"] == "COMPLETED"
    assert not target.exists()

    messages = _history(client, conversation_id)
    states = [m["role"] for m in messages]
    # turn 1: user + awaiting tool event + assistant; turn 2: tool + assistant
    assert states == ["user", "tool", "assistant", "tool", "assistant"]
    assert '"state": "AWAITING_APPROVAL"' in messages[1]["content"]
    assert '"state": "COMPLETED"' in messages[3]["content"]


def test_reject_records_cancellation_without_execution(client, tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "keepme.txt"
    target.write_text("precious", encoding="utf-8")

    first = client.post("/api/v1/chat", json={"message": "delete keepme.txt"})
    approval_id = first.json()["data"]["pending_approval"]["approval_id"]

    rejected = client.post(f"/api/v1/chat/approvals/{approval_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["data"]["tool"]["state"] == "REJECTED"
    assert "cancelled" in rejected.json()["data"]["content"]
    assert target.read_text(encoding="utf-8") == "precious"


def test_traversal_proposal_is_refused_honestly(client, tmp_path) -> None:
    response = client.post(
        "/api/v1/chat", json={"message": "read ../../etc/passwd"}
    )
    data = response.json()["data"]
    assert data["tool"]["state"] == "DENIED"
    assert "did not perform" in data["content"]
    assert data["pending_approval"] is None


def test_decision_for_unknown_approval_is_404(client) -> None:
    response = client.post(
        "/api/v1/chat/approvals/nope/approve", json={"approved": True}
    )
    assert response.status_code == 404


def test_malformed_proposal_gets_honest_no_action_reply(
    client, monkeypatch
) -> None:
    from app.infrastructure.inference_stub import StubInference

    def broken_proposal(self, prompt: str) -> str:
        return "<tool_request>{not valid json</tool_request>"

    monkeypatch.setattr(StubInference, "complete", broken_proposal)
    response = client.post("/api/v1/chat", json={"message": "read x.txt"})
    data = response.json()["data"]
    assert "took no action" in data["content"]
    assert data["tool"] is None


def test_tool_role_messages_are_excluded_from_plain_listing_contract(
    client, tmp_path
) -> None:
    """docs/06 §19: internal/tool roles must not render as normal messages.

    The detail endpoint returns them with role="tool" so the UI can decide;
    they must never appear as user/assistant prose.
    """
    workspace = tmp_path / "workspace"
    (workspace / "a.txt").write_text("A", encoding="utf-8")
    data = client.post("/api/v1/chat", json={"message": "read a.txt"}).json()["data"]
    messages = _history(client, data["conversation_id"])
    for message in messages:
        assert message["role"] in {"user", "assistant", "tool"}
        if message["role"] == "tool":
            assert message["content"].startswith("{")
