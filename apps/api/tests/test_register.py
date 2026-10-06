from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from tests.conftest import csrf_from_client
from tests.helpers import create_user

REGISTER_URL = "/api/v1/auth/register"


def _payload(email="new@example.com", password="password123", display_name="New User"):
    return {"email": email, "password": password, "display_name": display_name}


async def test_register_creates_session_and_user(client):
    resp = await client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == "new@example.com"
    assert body["user"]["role"] == UserRole.regular.value
    assert body["csrf_token"]

    assert "sofee_session" in client.cookies
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


async def test_register_email_lowercased(client):
    resp = await client.post(REGISTER_URL, json=_payload(email="NeW@Test.com"))
    assert resp.status_code == 201, resp.text
    async with async_session_factory() as db:
        user = (
            await db.execute(select(User).where(User.email == "new@test.com"))
        ).scalar_one_or_none()
    assert user is not None


async def test_register_duplicate_email_conflict(client):
    await create_user(email="new@example.com")
    resp = await client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 409, resp.text


async def test_register_duplicate_case_insensitive(client):
    await create_user(email="new@example.com")
    resp = await client.post(
        REGISTER_URL, json=_payload(email="NEW@EXAMPLE.COM")
    )
    assert resp.status_code == 409


async def test_register_password_same_as_email(client):
    resp = await client.post(REGISTER_URL, json=_payload(password="new@example.com"))
    assert resp.status_code == 400


async def test_register_short_password_validation(client):
    resp = await client.post(REGISTER_URL, json=_payload(password="short"))
    assert resp.status_code == 422


async def test_register_missing_display_name_validation(client):
    resp = await client.post(
        REGISTER_URL, json={"email": "new@example.com", "password": "password123"}
    )
    assert resp.status_code == 422


async def test_register_emits_audit_user_created(client):
    resp = await client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 201
    async with async_session_factory() as db:
        entry = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "user.created")
            )
        ).scalar_one_or_none()
        assert entry is not None
        assert entry.resource_id == resp.json()["user"]["id"]


async def test_register_emits_conflict_audit(client):
    await create_user(email="new@example.com")
    resp = await client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 409
    async with async_session_factory() as db:
        entry = (
            await db.execute(
                select(AuditLog).where(AuditLog.action == "user.register_conflict")
            )
        ).scalar_one_or_none()
        assert entry is not None


async def test_register_conflicts_rate_limited(client):
    await create_user(email="new@example.com")
    for _ in range(5):
        resp = await client.post(REGISTER_URL, json=_payload())
        assert resp.status_code == 409
    resp = await client.post(REGISTER_URL, json=_payload())
    assert resp.status_code == 429


async def test_register_new_user_has_no_admin_access(client):
    await client.post(REGISTER_URL, json=_payload())
    resp = await client.get(
        "/api/v1/admin/users", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 403