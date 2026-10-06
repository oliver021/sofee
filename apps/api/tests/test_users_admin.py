from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from tests.conftest import csrf_from_client
from tests.helpers import create_user, insert_session, login_through_api


def admin_client(client, email="admin@example.com"):
    return create_user(email=email, role=UserRole.admin)


async def test_patch_user_role_requires_csrf(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}", json={"role": "admin"}
    )
    assert resp.status_code == 403


async def test_patch_user_role(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "admin"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    async with async_session_factory() as db:
        row = await db.get(User, target.id)
        assert row.role is UserRole.admin


async def test_patch_user_role_ignores_unchanged(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "regular"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "regular"


async def test_patch_user_deactivate_and_reactivate(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    csrf = csrf_from_client(client)
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"is_active": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


async def test_patch_user_404(client):
    admin = await admin_client(client)
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000000",
        json={"role": "admin"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404


async def test_patch_cannot_deactivate_self(client):
    admin = await admin_client(client)
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 400


async def test_patch_cannot_demote_self(client):
    admin = await admin_client(client)
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"role": "regular"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 400


async def test_patch_role_and_deactivate_audited(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "admin", "is_active": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(AuditLog).where(AuditLog.resource_id == str(target.id))
            )
        ).scalars().all()
    actions = {r.action for r in rows}
    assert {"user.role_changed", "user.deactivated"} <= actions


async def test_patch_deactivated_user_cannot_login(client):
    admin = await admin_client(client)
    target = await create_user(email="victim@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    client.cookies.clear()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "victim@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_list_users_search(client):
    admin = await admin_client(client, email="admin@example.com")
    await create_user(email="ana@example.com", display_name="Ana López")
    await create_user(email="bruno@example.com")
    session = await insert_session(admin.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
    resp = await client.get("/api/v1/admin/users", params={"q": "ana"})
    emails = [u["email"] for u in resp.json()]
    assert emails == ["ana@example.com"]
    resp = await client.get("/api/v1/admin/users", params={"q": "López"})
    assert [u["email"] for u in resp.json()] == ["ana@example.com"]


async def test_login_response_includes_csrf_token(client):
    await login_through_api(client)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["csrf_token"] == csrf_from_client(client)


async def test_csrf_endpoint_returns_token(client):
    user = await create_user()
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/auth/csrf")
    assert resp.status_code == 200
    assert resp.json()["token"] == csrf_from_client(client)


async def test_csrf_endpoint_requires_auth(client):
    resp = await client.get("/api/v1/auth/csrf")
    assert resp.status_code == 401