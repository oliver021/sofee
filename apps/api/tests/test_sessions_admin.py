import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.session import Session
from app.models.user import UserRole
from tests.conftest import csrf_from_client
from tests.helpers import create_user, insert_session


async def admin_client(client, email="admin@example.com"):
    admin = await create_user(email=email, role=UserRole.admin)
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    return admin


async def test_list_user_sessions_requires_admin(client):
    await create_user()
    resp = await client.get(
        f"/api/v1/admin/users/{uuid.uuid4()}/sessions"
    )
    assert resp.status_code == 401


async def test_list_user_sessions_active_only(client):
    target = await create_user(email="victim@example.com", role=UserRole.admin)
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    session = await insert_session(target.id)
    await insert_session(target.id, revoked=True)
    await insert_session(target.id, expired=True)
    s = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(s.id))
    resp = await client.get(f"/api/v1/admin/users/{target.id}/sessions")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert ids == [str(session.id)]


async def test_list_user_sessions_unknown_user(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    s = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(s.id))
    resp = await client.get(
        f"/api/v1/admin/users/{uuid.uuid4()}/sessions"
    )
    assert resp.status_code == 404


async def test_revoke_any_session(client):
    target = await create_user(email="victim@example.com")
    victim_session = await insert_session(target.id)
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    csrf = csrf_from_client(client)

    resp = await client.delete(f"/api/v1/admin/sessions/{victim_session.id}", headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 204
    async with async_session_factory() as db:
        row = await db.get(Session, victim_session.id)
        assert row.revoked_at is not None


async def test_revoke_own_current_session_rejected(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    resp = await client.delete(
        f"/api/v1/admin/sessions/{admin_session.id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 400


async def test_revoke_unknown_session(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    s = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(s.id))
    resp = await client.delete(
        f"/api/v1/admin/sessions/{uuid.uuid4()}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404


async def test_revoke_any_session_requires_csrf(client):
    target = await create_user(email="victim@example.com")
    victim_session = await insert_session(target.id)
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    resp = await client.delete(f"/api/v1/admin/sessions/{victim_session.id}")
    assert resp.status_code == 403


async def test_revoke_all_user_sessions(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    target = await create_user(email="victim@example.com")
    s1 = await insert_session(target.id)
    s2 = await insert_session(target.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/revoke-sessions",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Session).where(Session.user_id == target.id)
            )
        ).scalars().all()
        assert all(r.revoked_at is not None for r in rows)


async def test_revoke_all_on_self_keeps_current_session(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    current = await insert_session(admin.id)
    other = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(current.id))
    resp = await client.post(
        f"/api/v1/admin/users/{admin.id}/revoke-sessions",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    async with async_session_factory() as db:
        current_row = await db.get(Session, current.id)
        other_row = await db.get(Session, other.id)
        assert current_row.revoked_at is None
        assert other_row.revoked_at is not None
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 200


async def test_revoke_audited(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    target = await create_user(email="victim@example.com")
    s1 = await insert_session(target.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    resp = await client.delete(
        f"/api/v1/admin/sessions/{s1.id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    async with async_session_factory() as db:
        row = (await db.execute(
            select(AuditLog).where(AuditLog.action == "session.revoked").order_by(AuditLog.id.desc())
        )).scalars().first()
        assert row is not None
        assert row.resource_id == str(s1.id)
        assert row.data["target_user_id"] == str(target.id)


async def test_revoke_all_audited(client):
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    admin_session = await insert_session(admin.id)
    target = await create_user(email="victim@example.com")
    await insert_session(target.id)
    await insert_session(target.id)
    client.cookies.set("sofee_session", str(admin_session.id))
    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/revoke-sessions",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    async with async_session_factory() as db:
        row = (await db.execute(
            select(AuditLog).where(AuditLog.action == "user.sessions_revoked").order_by(AuditLog.id.desc())
        )).scalars().first()
        assert row is not None
        assert row.data["count"] == 2
        assert datetime.now(UTC) >= row.created_at