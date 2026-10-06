from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.user import UserRole
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user, insert_session, login_through_api


async def audit_rows():
    async with async_session_factory() as db:
        return (
            await db.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()


def _summary(rows):
    return [
        (r.action, r.resource_type, r.resource_id, str(r.actor_id) if r.actor_id else None, r.data)
        for r in rows
    ]


async def insert_audit(action: str, created_at: datetime) -> None:
    async with async_session_factory() as db:
        db.add(AuditLog(action=action, created_at=created_at))
        await db.commit()


# --- Escritura retroactiva sobre M1 (auth/sesiones) -------------------------

async def test_login_failure_logs_audit(client):
    user = await create_user(email="user@example.com")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrongpass123"},
    )
    assert resp.status_code == 401
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    action, rtype, rid, actor, data = rows[0]
    assert action == "user.login_failed"
    assert rtype == "user"
    assert rid == str(user.id)
    assert actor is None
    assert data == {"email": "user@example.com", "reason": "wrong_password"}


async def test_login_unknown_email_logs_audit(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "wrongpass123"},
    )
    assert resp.status_code == 401
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    assert rows[0][0] == "user.login_failed"
    assert rows[0][2] == "ghost@example.com"
    assert rows[0][4]["reason"] == "unknown_email"


async def test_login_success_leaves_no_audit(client):
    await login_through_api(client)
    assert await audit_rows() == []


async def test_logout_logs_session_revoked(client):
    user = await login_through_api(client)
    sid = client.cookies.get("sofee_session")
    resp = await client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 204
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    action, rtype, rid, actor, _ = rows[0]
    assert action == "session.revoked"
    assert rtype == "session"
    assert actor == user["id"]
    assert rid == sid


async def test_revoke_session_logs_audit(client):
    user = await login_through_api(client)
    second = await insert_session(user["id"])
    resp = await client.delete(
        f"/api/v1/me/sessions/{second.id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    action, rtype, rid, actor, _ = rows[0]
    assert action == "session.revoked"
    assert rtype == "session"
    assert rid == str(second.id)
    assert actor == user["id"]


# --- Escritura retroactiva sobre M2 (providers) -----------------------------

async def _create_provider(client, **overrides):
    payload = {"name": "DeepInfra prod", "kind": "deepinfra", **overrides}
    resp = await client.post(
        "/api/v1/admin/providers",
        json=payload,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_provider_logs_one_row(client):
    admin = await authed_client(client)
    await _create_provider(client)
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    action, rtype, rid, actor, data = rows[0]
    assert action == "provider.created"
    assert rtype == "provider"
    assert actor == str(admin.id)
    assert data == {"name": "DeepInfra prod", "kind": "deepinfra", "has_initial_key": False}


async def test_create_provider_with_initial_key_logs_one_row(client):
    await authed_client(client)
    await _create_provider(client, initial_api_key="sk-secret-9123")
    rows = _summary(await audit_rows())
    assert len(rows) == 1
    assert rows[0][0] == "provider.created"
    assert rows[0][4]["has_initial_key"] is True
    assert "sk-secret-9123" not in str(rows[0][4])


async def test_update_provider_logs_changes_and_redacts_headers(client):
    await authed_client(client)
    provider = await _create_provider(client)
    resp = await client.patch(
        f"/api/v1/admin/providers/{provider['id']}",
        json={
            "is_enabled": False,
            "default_headers": {"Authorization": "Bearer sekrit", "X-Trace": "abc"},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    rows = _summary(await audit_rows())
    updated = [r for r in rows if r[0] == "provider.updated"]
    assert len(updated) == 1
    _, rtype, rid, actor, data = updated[0]
    assert rtype == "provider"
    assert data["is_enabled"] is False
    assert data["default_headers"] == {"Authorization": "***", "X-Trace": "abc"}


async def test_failed_duplicate_update_leaves_no_audit(client):
    await authed_client(client)
    p1 = await _create_provider(client, name="A1")
    await _create_provider(client, name="B2")
    resp = await client.patch(
        f"/api/v1/admin/providers/{p1['id']}",
        json={"name": "B2"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 409
    actions = [a[0] for a in _summary(await audit_rows())]
    assert "provider.updated" not in actions


async def test_delete_provider_logs_row(client):
    await authed_client(client)
    provider = await _create_provider(client)
    resp = await client.delete(
        f"/api/v1/admin/providers/{provider['id']}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    rows = _summary(await audit_rows())
    deleted = [r for r in rows if r[0] == "provider.deleted"]
    assert len(deleted) == 1
    assert deleted[0][2] == provider["id"]
    assert deleted[0][4]["name"] == "DeepInfra prod"


async def test_rotate_credential_logs_row(client):
    await authed_client(client)
    provider = await _create_provider(client, initial_api_key="sk-first-0001")
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/credentials",
        json={"api_key": "sk-second-0002"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    rotated = [r for r in _summary(await audit_rows()) if r[0] == "provider.credential_rotated"]
    assert len(rotated) == 1
    assert rotated[0][2] == provider["id"]
    assert rotated[0][4] == {"last_four": "0002", "previous_last_four": "0001"}


@respx.mock
async def test_sync_models_logs_row(client):
    await authed_client(client)
    provider = await _create_provider(client, initial_api_key="sk-x")
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})
    )
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/models/sync",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    synced = [r for r in _summary(await audit_rows()) if r[0] == "provider.models_synced"]
    assert len(synced) == 1
    assert synced[0][2] == provider["id"]
    assert synced[0][4] == {"created": 2, "already_exists": 0, "total": 2}


@respx.mock
async def test_toggle_model_logs_row(client):
    await authed_client(client)
    provider = await _create_provider(client, initial_api_key="sk-x")
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "model-a"}]})
    )
    sync = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/models/sync",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    model = sync.json()["models"][0]
    resp = await client.patch(
        f"/api/v1/admin/providers/{provider['id']}/models/{model['id']}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    toggled = [r for r in _summary(await audit_rows()) if r[0] == "provider.model_toggled"]
    assert len(toggled) == 1
    assert toggled[0][2] == provider["id"]
    assert toggled[0][4] == {"model_id": "model-a", "display_name": "model-a", "is_enabled": False}


# --- Endpoint GET /admin/audit ----------------------------------------------

async def test_audit_requires_admin(client):
    resp = await client.get("/api/v1/admin/audit")
    assert resp.status_code == 401
    await authed_client(client, role=UserRole.regular)
    resp = await client.get("/api/v1/admin/audit")
    assert resp.status_code == 403


async def test_audit_lists_newest_first_with_actor_email(client):
    admin = await authed_client(client)
    await _create_provider(client)
    resp = await client.get("/api/v1/admin/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["action"] == "provider.created"
    assert item["actor_id"] == str(admin.id)
    assert item["actor_email"] == admin.email
    assert item["resource_type"] == "provider"
    assert item["metadata"]["name"] == "DeepInfra prod"


async def test_audit_filter_by_action(client):
    await authed_client(client)
    provider = await _create_provider(client)
    await client.patch(
        f"/api/v1/admin/providers/{provider['id']}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    resp = await client.get("/api/v1/admin/audit", params={"action": "provider.updated"})
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] == "provider.updated"


async def test_audit_filter_by_actor(client):
    admin = await create_user(email="admin1@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    other = await create_user(email="admin2@example.com", role=UserRole.admin)
    other_session = await insert_session(other.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    await client.post(
        "/api/v1/admin/providers",
        json={"name": "P1", "kind": "deepinfra"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    resp = await client.get("/api/v1/admin/audit", params={"actor_id": str(admin.id)})
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["actor_id"] == str(admin.id)
    client.cookies.set("sofee_session", str(other_session.id))
    resp = await client.get("/api/v1/admin/audit", params={"actor_id": str(other.id)})
    assert resp.json()["items"] == []


async def test_audit_date_range_filter(client):
    await authed_client(client)
    base = datetime.now(UTC) - timedelta(days=1)
    await insert_audit("test.old", base - timedelta(hours=1))
    await insert_audit("test.mid", base + timedelta(hours=12))
    await insert_audit("test.new", base + timedelta(hours=47))
    resp = await client.get(
        "/api/v1/admin/audit",
        params={
            "start": base.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "end": (base + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        },
    )
    assert resp.status_code == 200, resp.json()
    items = resp.json()["items"]
    assert [i["action"] for i in items] == ["test.mid"]


async def test_audit_invalid_cursor_400(client):
    await authed_client(client)
    resp = await client.get("/api/v1/admin/audit", params={"cursor": "not-a-valid-cursor"})
    assert resp.status_code == 400


async def test_audit_cursor_pagination(client):
    await authed_client(client)
    base = datetime.now(UTC) - timedelta(days=1)
    for i in range(5):
        await insert_audit(f"test.entry.{i}", base + timedelta(minutes=i))

    page1 = await client.get("/api/v1/admin/audit", params={"limit": 2, "action": "test.entry.0"})
    # action filter only matches one; paginate sin filtro para probar el cursor
    collected: list[dict] = []
    cursor = None
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = await client.get("/api/v1/admin/audit", params=params)
        assert resp.status_code == 200
        body = resp.json()
        collected.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    actions = [i["action"] for i in collected]
    assert actions == [f"test.entry.{i}" for i in range(4, -1, -1)]
    assert len(collected) == 5