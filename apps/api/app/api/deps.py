from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..core.csrf import verify_csrf_token
from ..db import get_session
from ..models.session import Session
from ..models.user import User, UserRole


@dataclass
class AuthContext:
    user: User
    session: Session


def client_ip(request: Request) -> str | None:
    """IP del cliente real.

    X-Forwarded-For solo se admite cuando el peer directo está en TRUSTED_PROXIES;
    en cualquier otro caso se usa la IP del socket, para que ni la auditoría ni el
    rate limit se dejen spoofear por una cabecera arbitraria.
    """
    forwarded = request.headers.get("x-forwarded-for")
    peername = request.client.host if request.client else None
    if forwarded and peername and peername in settings.trusted_proxies:
        return forwarded.split(",")[0].strip()
    return peername


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_auth(
    request: Request, db: AsyncSession = Depends(get_session)
) -> AuthContext:
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        raise _unauthorized()
    try:
        session_id = uuid.UUID(raw)
    except ValueError:
        raise _unauthorized()

    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.user))
    )
    sess = result.scalar_one_or_none()
    if sess is None:
        raise _unauthorized()
    if sess.revoked_at is not None:
        raise _unauthorized()

    now = datetime.now(UTC)
    if sess.expires_at <= now:
        raise _unauthorized()

    user = sess.user
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    sess.expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    await db.commit()

    return AuthContext(user=user, session=sess)


def require_user(auth: AuthContext = Depends(get_current_auth)) -> User:
    return auth.user


def require_admin(auth: AuthContext = Depends(get_current_auth)) -> User:
    if auth.user.role is not UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return auth.user


async def check_csrf(
    request: Request, auth: AuthContext = Depends(get_current_auth)
) -> None:
    token = request.headers.get("X-CSRF-Token")
    if not verify_csrf_token(auth.session.id, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return None