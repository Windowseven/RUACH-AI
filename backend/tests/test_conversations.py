import uuid


def test_create_conversation_returns_201_envelope(client):
    response = client.post("/api/v1/conversations", json={"title": "Python debugging"})
    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["data"]["id"])
    assert body["data"]["title"] == "Python debugging"
    assert body["request_id"] == response.headers["x-request-id"]


def test_created_conversation_appears_in_listing(client):
    created = client.post("/api/v1/conversations", json={"title": "Second"}).json()["data"]
    listing = client.get("/api/v1/conversations")
    assert listing.status_code == 200
    items = listing.json()["data"]
    assert [item["id"] for item in items] == [created["id"]]
    assert set(items[0].keys()) == {"id", "title", "created_at"}


def test_get_conversation_detail_includes_empty_messages(client):
    created = client.post("/api/v1/conversations", json={"title": "Detail"}).json()["data"]
    detail = client.get(f"/api/v1/conversations/{created['id']}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["messages"] == []
    assert data["title"] == "Detail"


def test_get_unknown_conversation_returns_structured_404(client):
    response = client.get("/api/v1/conversations/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


def test_delete_then_get_yields_404(client):
    created = client.post("/api/v1/conversations", json={"title": "Doomed"}).json()["data"]
    deleted = client.delete(f"/api/v1/conversations/{created['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/conversations/{created['id']}").status_code == 404


def test_blank_title_triggers_validation_error(client):
    response = client.post("/api/v1/conversations", json={"title": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any("title" in detail for detail in body["error"]["details"])
