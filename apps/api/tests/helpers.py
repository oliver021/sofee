from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.db import async_session_factory
from app.models.session import Session
from app.models.user import User, UserRole


async def insert_session(user_id, *, revoked=False, expired=False, expires_in=None):
    async with async_session_factory() as db:
        if expires_in is None:
            expires_in = timedelta(days=30)
        if expired:
            expires_in = -timedelta(seconds=1)
        session = Session(
            user_id=user_id,
            expires_at=datetime.now(UTC) + expires_in,
            revoked_at=datetime.now(UTC) if revoked else None,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session


async def create_user(
    email: str = "user@example.com",
    password: str = "password123",
    role: UserRole = UserRole.regular,
    display_name: str = "Test User",
    is_active: bool = True,
) -> User:
    async with async_session_factory() as db:
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
            is_active=is_active,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def login_through_api(client, email="user@example.com", password="password123"):
    await create_user(email=email, password=password)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email.lower(), "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["user"]


async def authed_client(client, role=UserRole.admin):
    """Setea una cookie de sesión válida para un usuario recién creado."""
    user = await create_user(role=role)
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    return user