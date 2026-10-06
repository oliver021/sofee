from datetime import timedelta

from sqlalchemy import select

from app.db import async_session_factory
from app.models.session import Session
from tests.conftest import csrf_from_client
from tests.helpers import create_user, insert_session, login_through_api


async def test_login_success_sets_cookie(client):
    await login_through_api(client)
    assert "sofee_session" in client.cookies


async def test_login_email_case_insensitive(client):
    await login_through_api(client, email="Case@Test.com")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "case@test.com", "password": "password123"},
    )
    assert resp.status_code == 200


async def test_login_wrong_password(client):
    await create_user()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrongpass123"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_login_inactive_user(client):
    await create_user(is_active=False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_login_short_password_validation(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_me_without_auth(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_me_with_cookie(client):
    user = await login_through_api(client)
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]


async def test_logout_revokes_session(client):
    await login_through_api(client)
    resp = await client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 204
    assert client.cookies.get("sofee_session") is None
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_logout_without_csrf_rejected(client):
    await login_through_api(client)
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 403


async def test_sessions_list_and_revoke(client):
    user = await login_through_api(client)
    second = await insert_session(user["id"])
    resp = await client.get("/api/v1/me/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2

    resp = await client.delete(
        f"/api/v1/me/sessions/{second.id}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    resp = await client.get("/api/v1/me/sessions")
    remaining_ids = [s["id"] for s in resp.json()]
    assert len(remaining_ids) == 1
    assert str(second.id) not in remaining_ids


async def test_revoke_unknown_session_404(client):
    await login_through_api(client)
    resp = await client.delete(
        "/api/v1/me/sessions/00000000-0000-0000-0000-000000000000",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404


async def test_expired_session_rejected(client):
    user = await create_user()
    session = await insert_session(user.id, expired=True)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_revoked_session_rejected(client):
    user = await create_user()
    session = await insert_session(user.id, revoked=True)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_garbage_cookie_rejected(client):
    client.cookies.set("sofee_session", "not-a-uuid")
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


async def test_sliding_expiration_extends(client):
    user = await create_user()
    session = await insert_session(user.id, expires_in=timedelta(days=1))
    client.cookies.set("sofee_session", str(session.id))
    await client.get("/api/v1/me")
    async with async_session_factory() as db:
        stored = (
            await db.execute(select(Session).where(Session.id == session.id))
        ).scalar_one()
        assert stored.expires_at > session.expires_at


async def test_inactive_user_session_rejected(client):
    user = await create_user(is_active=False)
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 403