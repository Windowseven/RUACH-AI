from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_chat_creates_conversation_and_persists_two_messages(client):
    response = client.post("/api/v1/chat", json={"message": "Explain this Python error."})
    assert response.status_code == 200
    body = response.json()
    assert set(body["data"].keys()) == {"message_id", "conversation_id", "role", "content"}
    assert body["data"]["role"] == "assistant"
    assert "[stub]" in body["data"]["content"]

    detail = client.get(f"/api/v1/conversations/{body['data']['conversation_id']}")
    messages = detail.json()["data"]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_chat_with_existing_conversation_appends(client):
    first = client.post("/api/v1/chat", json={"message": "hello"}).json()["data"]
    second = client.post(
        "/api/v1/chat",
        json={"message": "again", "conversation_id": first["conversation_id"]},
    )
    assert second.status_code == 200
    assert second.json()["data"]["conversation_id"] == first["conversation_id"]

    detail = client.get(f"/api/v1/conversations/{first['conversation_id']}")
    roles = [m["role"] for m in detail.json()["data"]["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_chat_into_unknown_conversation_returns_structured_404(client):
    response = client.post("/api/v1/chat", json={"message": "hi", "conversation_id": "missing-id"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_blank_message_triggers_validation_error(client):
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any("message" in detail for detail in body["error"]["details"])
