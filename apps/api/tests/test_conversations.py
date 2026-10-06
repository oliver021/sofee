import pytest

from tests.conftest import csrf_from_client
from tests.helpers import login_through_api


async def _new_thread(client):
    resp = await client.post(
        "/api/v1/threads",
        json={"client_id": "thread-abc", "title": "My thread", "mode": "research"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _post_message(client, thread_id, message_id="msg-1", **overrides):
    payload = {
        "client_id": message_id,
        "role": "user",
        "text": "Hello",
        "status": "complete",
        **overrides,
    }
    return await client.post(
        f"/api/v1/threads/{thread_id}/messages",
        json=payload,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


async def test_create_thread(client):
    await login_through_api(client)
    body = await _new_thread(client)
    assert body["id"] == "thread-abc"
    assert body["title"] == "My thread"
    assert body["mode"] == "research"
    assert body["message_count"] == 0


async def test_upsert_thread_is_idempotent(client):
    await login_through_api(client)
    await _new_thread(client)
    body = await _new_thread(client)
    assert body["id"] == "thread-abc"
    list_resp = await client.get("/api/v1/threads")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_list_threads_orders_by_updated(client):
    await login_through_api(client)
    await _new_thread(client)
    second = await client.post(
        "/api/v1/threads",
        json={"client_id": "thread-xyz"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert second.status_code == 201
    resp = await client.get("/api/v1/threads")
    assert [(t["id"], t["message_count"]) for t in resp.json()] == [
        ("thread-xyz", 0),
        ("thread-abc", 0),
    ]

    await _post_message(client, "thread-abc")
    resp = await client.get("/api/v1/threads")
    rows = [(t["id"], t["message_count"]) for t in resp.json()]
    assert rows == [("thread-abc", 1), ("thread-xyz", 0)]


async def test_thread_isolation_between_users(client):
    await login_through_api(client)
    await _new_thread(client)
    await login_through_api(client, email="other@example.com")
    resp = await client.get("/api/v1/threads")
    assert resp.json() == []


async def test_get_thread_detail_orders_messages(client):
    await login_through_api(client)
    await _new_thread(client)
    for i in range(1, 4):
        resp = await _post_message(client, "thread-abc", message_id=f"msg-{i}")
        assert resp.status_code == 201, resp.text
    resp = await client.get("/api/v1/threads/thread-abc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message_count"] == 3
    assert [m["id"] for m in body["messages"]] == ["msg-1", "msg-2", "msg-3"]
    seqs = [m["seq"] for m in body["messages"]]
    assert seqs == sorted(seqs)


async def test_message_roundtrip_fields(client):
    await login_through_api(client)
    await _new_thread(client)
    resp = await _post_message(
        client,
        "thread-abc",
        role="assistant",
        text="Final answer",
        status="stopped",
        citations=[{"title": "src", "url": "https://example.com"}],
        attachment_ids=["file-1", "file-2"],
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "assistant"
    assert body["text"] == "Final answer"
    assert body["status"] == "stopped"
    assert body["citations"][0]["title"] == "src"
    assert body["attachment_ids"] == ["file-1", "file-2"]


async def test_message_upsert_updates_in_place(client):
    await login_through_api(client)
    await _new_thread(client)
    await _post_message(client, "thread-abc", text="First")
    resp = await _post_message(
        client, "thread-abc", message_id="msg-2", text="Assistant", role="assistant"
    )
    first_seq = resp.json()["seq"]

    upsert = await _post_message(
        client,
        "thread-abc",
        message_id="msg-2",
        text="Assistant v2",
        role="assistant",
        status="stopped",
    )
    assert upsert.status_code == 201
    body = upsert.json()
    assert body["text"] == "Assistant v2"
    assert body["seq"] == first_seq

    detail = (await client.get("/api/v1/threads/thread-abc")).json()
    assert [m["text"] for m in detail["messages"]] == ["First", "Assistant v2"]
    assert len(detail["messages"]) == 2


async def test_patch_thread_updates_title_and_mode(client):
    await login_through_api(client)
    await _new_thread(client)
    resp = await client.patch(
        "/api/v1/threads/thread-abc",
        json={"title": "Renamed", "mode": "explore"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Renamed"
    assert body["mode"] == "explore"


async def test_delete_thread_removes_messages(client):
    await login_through_api(client)
    await _new_thread(client)
    await _post_message(client, "thread-abc")
    resp = await client.delete(
        "/api/v1/threads/thread-abc",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    assert (await client.get("/api/v1/threads/thread-abc")).status_code == 404


async def test_delete_message(client):
    await login_through_api(client)
    await _new_thread(client)
    await _post_message(client, "thread-abc", message_id="msg-1")
    await _post_message(client, "thread-abc", message_id="msg-2")
    resp = await client.delete(
        "/api/v1/threads/thread-abc/messages/msg-1",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    detail = (await client.get("/api/v1/threads/thread-abc")).json()
    assert [m["id"] for m in detail["messages"]] == ["msg-2"]


async def test_unknown_thread_404(client):
    await login_through_api(client)
    for method, path in [
        ("GET", "/api/v1/threads/nope"),
        ("PATCH", "/api/v1/threads/nope"),
        ("DELETE", "/api/v1/threads/nope"),
        ("POST", "/api/v1/threads/nope/messages"),
    ]:
        resp = await client.request(
            method,
            path,
            headers={"X-CSRF-Token": csrf_from_client(client)},
            json={"client_id": "msg-x", "role": "user", "text": "hi"},
        )
        assert resp.status_code == 404, (method, path)


async def test_conversations_401_without_auth(client):
    for method, path in [
        ("GET", "/api/v1/threads"),
        ("POST", "/api/v1/threads"),
        ("GET", "/api/v1/threads/x"),
        ("DELETE", "/api/v1/threads/x"),
        ("POST", "/api/v1/threads/x/messages"),
        ("DELETE", "/api/v1/threads/x/messages/m"),
    ]:
        resp = await client.request(method, path, json={})
        assert resp.status_code == 401, (method, path)


async def test_conversation_mutations_require_csrf(client):
    await login_through_api(client)
    resp = await client.post("/api/v1/threads", json={"client_id": "t1"})
    assert resp.status_code == 403
    await _new_thread(client)
    resp = await client.post(
        "/api/v1/threads/t1/messages",
        json={"client_id": "m1", "role": "user", "text": "hi"},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("role", ["admin", "system", "anything"])
async def test_invalid_message_role_rejected(client, role):
    await login_through_api(client)
    await _new_thread(client)
    resp = await _post_message(
        client, "thread-abc", role=role, message_id="msg-1"
    )
    assert resp.status_code == 422