from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.models.login_attempt import LoginAttempt
from tests.helpers import create_user

MAX = settings.login_rate_limit_max_attempts
UUID = "00000000-0000-0000-0000-000000000000"


async def _login(client, email="user@example.com", password="wrongpass123", forwarded=None):
    headers = {"X-Forwarded-For": forwarded} if forwarded else None
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )


async def test_successful_login_not_rate_limited(client):
    await create_user()
    resp = await _login(client, password="password123")
    assert resp.status_code == 200


async def test_blocks_after_max_failures(client):
    await create_user()
    for _ in range(MAX):
        resp = await _login(client)
        assert resp.status_code == 401

    blocked = await _login(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


async def test_blocked_even_with_correct_password(client):
    """Mientras el límite siga superado, ni la contraseña correcta entra."""
    await create_user()
    for _ in range(MAX):
        await _login(client)

    resp = await _login(client, password="password123")
    assert resp.status_code == 429


async def test_rate_limit_isolates_per_email_across_ips(client):
    """El atacante no esquiva el límite cambiando de IP: cuenta por email."""
    await create_user(email="target@example.com")
    for i in range(MAX):
        resp = await _login(client, email="target@example.com", forwarded=f"10.0.0.{i}")
        assert resp.status_code == 401

    blocked = await _login(client, email="target@example.com", forwarded="10.0.0.99")
    assert blocked.status_code == 429


async def test_old_attempts_outside_window_do_not_block(client):
    """Podadas por la limpieza perezosa: no cuentan los fallos fuera de la ventana."""
    await create_user()
    old = datetime.now(UTC) - timedelta(hours=1)
    async with async_session_factory() as db:
        for _ in range(500):
            db.add(
                LoginAttempt(
                    email="user@example.com", ip_address="9.9.9.9", success=False, created_at=old
                )
            )
        await db.commit()

    resp = await _login(client)
    assert resp.status_code == 401


async def test_successful_logins_do_not_count(client):
    """Solo fallos cuentan; logins válidos desde la misma IP no alimentan el límite."""
    for i in range(MAX + 1):
        await create_user(email=f"u{i}@example.com")

    for i in range(MAX + 1):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": f"u{i}@example.com", "password": "password123"},
        )
        assert resp.status_code == 200

    resp = await _login(client)
    assert resp.status_code == 401


async def test_attempts_are_recorded(client):
    await create_user()
    await _login(client)
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(LoginAttempt).order_by(LoginAttempt.id)))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].email == "user@example.com"
    assert rows[0].ip_address == "127.0.0.1"
    assert rows[0].success is False