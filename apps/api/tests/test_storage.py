from pathlib import Path

from sqlalchemy import select, text

from app.db import async_session_factory
from app.models.storage import StorageObject
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user, insert_session


async def _storage_rows():
    async with async_session_factory() as db:
        return (await db.execute(select(StorageObject))).scalars().all()


async def _storage_key(obj_id: str) -> str:
    async with async_session_factory() as db:
        return (
            await db.execute(select(StorageObject.storage_key).where(StorageObject.id == obj_id))
        ).scalar_one()


def _upload(client, filename="report.pdf", data=b"pdf-content-123", content_type="application/pdf"):
    return client.post(
        "/api/v1/storage",
        files={"file": (filename, data, content_type)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


# --- Auth / RBAC ------------------------------------------------------------

async def test_upload_requires_auth(client):
    resp = await client.post("/api/v1/storage", files={"file": ("a.txt", b"x", "text/plain")})
    assert resp.status_code == 401


async def test_upload_requires_csrf(client):
    await authed_client(client)
    resp = await client.post("/api/v1/storage", files={"file": ("a.txt", b"x", "text/plain")})
    assert resp.status_code == 403


async def test_download_requires_auth(client):
    resp = await client.get("/api/v1/storage/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


async def test_delete_requires_auth(client):
    resp = await client.delete("/api/v1/storage/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


# --- Upload / download ------------------------------------------------------

async def test_upload_and_download_roundtrip(client):
    await authed_client(client)
    resp = await _upload(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["filename"] == "report.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(b"pdf-content-123")

    resp = await client.get(f"/api/v1/storage/{body['id']}")
    assert resp.status_code == 200
    assert resp.content == b"pdf-content-123"
    assert resp.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''report.pdf" in resp.headers["content-disposition"]

    rows = await _storage_rows()
    assert len(rows) == 1
    key = rows[0].storage_key
    assert (Path("/tmp/sofee-test-storage") / key).read_bytes() == b"pdf-content-123"


async def test_upload_logs_audit(client):
    await authed_client(client)
    resp = await _upload(client)
    assert resp.status_code == 201
    async with async_session_factory() as db:
        action = (await db.execute(text("SELECT action FROM audit_log"))).scalar_one()
        assert action == "storage.object_uploaded"


async def test_upload_too_large(client):
    await authed_client(client)
    resp = await client.post(
        "/api/v1/storage",
        files={"file": ("big.txt", b"x" * 1500, "text/plain")},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 413


# --- Owner isolation / borrado ----------------------------------------------

async def test_download_owner_only(client):
    user_a = await authed_client(client)
    resp = await _upload(client)
    assert resp.status_code == 201
    obj_id = resp.json()["id"]

    user_b = await create_user(email="other@example.com")
    session_b = await insert_session(user_b.id)
    client.cookies.set("sofee_session", str(session_b.id))
    resp = await client.get(f"/api/v1/storage/{obj_id}")
    assert resp.status_code == 404
    assert user_a.id != user_b.id


async def test_delete_removes_bytes_and_marks_deleted(client):
    await authed_client(client)
    obj_id = (await _upload(client)).json()["id"]
    key = await _storage_key(obj_id)

    resp = await client.delete(
        f"/api/v1/storage/{obj_id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204

    assert not (Path("/tmp/sofee-test-storage") / key).exists()
    resp = await client.get(f"/api/v1/storage/{obj_id}")
    assert resp.status_code == 404

    async with async_session_factory() as db:
        obj = (
            await db.execute(select(StorageObject).where(StorageObject.id == obj_id))
        ).scalar_one()
        assert obj.deleted_at is not None

    async with async_session_factory() as db:
        actions = (await db.execute(text("SELECT action FROM audit_log"))).scalars().all()
        assert actions == ["storage.object_uploaded", "storage.object_deleted"]


async def test_delete_requires_csrf(client):
    await authed_client(client)
    obj_id = (await _upload(client)).json()["id"]
    resp = await client.delete(f"/api/v1/storage/{obj_id}")
    assert resp.status_code == 403


async def test_delete_owner_only(client):
    await authed_client(client)
    obj_id = (await _upload(client)).json()["id"]

    other = await create_user(email="other@example.com")
    other_session = await insert_session(other.id)
    client.cookies.set("sofee_session", str(other_session.id))
    resp = await client.delete(
        f"/api/v1/storage/{obj_id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404


async def test_unknown_object_404(client):
    await authed_client(client)
    resp = await client.get("/api/v1/storage/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    resp = await client.delete(
        "/api/v1/storage/00000000-0000-0000-0000-000000000000",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404