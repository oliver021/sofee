from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...core.csrf import derive_csrf_token
from ...core.security import hash_password, password_is_valid, verify_password
from ...db import get_session
from ...models.session import Session
from ...models.user import User, UserRole
from ...schemas import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserOut,
)
from ...services.audit import write_audit
from ...services.ratelimit import (
    login_rate_limit_retry_after,
    record_login_attempt,
)
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, session_id, expires_at: datetime) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=str(session_id),
        max_age=settings.session_ttl_seconds,
        expires=expires_at,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    ip = client_ip(request)

    retry_after = await login_rate_limit_retry_after(
        db, email=payload.email, ip=ip
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        reason = (
            "unknown_email"
            if user is None
            else "inactive"
            if not user.is_active
            else "wrong_password"
        )
        record_login_attempt(db, email=payload.email, ip=ip, success=False)
        await write_audit(
            db,
            action="user.login_failed",
            actor_id=None,
            resource_type="user",
            resource_id=str(user.id) if user is not None else payload.email.lower(),
            data={"email": payload.email.lower(), "reason": reason},
            ip_address=ip,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    record_login_attempt(db, email=payload.email, ip=ip, success=True)

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    session = Session(
        user_id=user.id,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    db.add(session)
    await db.flush()

    user.last_login_at = now
    await db.commit()

    _set_session_cookie(response, session.id, expires_at)
    return LoginResponse(
        user=UserOut.model_validate(user), csrf_token=derive_csrf_token(session.id)
    )


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    ip = client_ip(request)
    email = payload.email.lower()

    retry_after = await login_rate_limit_retry_after(db, email=email, ip=ip)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    password_error = password_is_valid(payload.password, email)
    if password_error is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_error)

    display_name = payload.display_name.strip() or email.split("@")[0]

    async def _conflict() -> HTTPException:
        record_login_attempt(db, email=email, ip=ip, success=False)
        await write_audit(
            db,
            action="user.register_conflict",
            actor_id=None,
            resource_type="user",
            resource_id=email,
            data={"email": email, "reason": "email_taken"},
            ip_address=ip,
        )
        await db.commit()
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    existing = (
        await db.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise await _conflict()

    now = datetime.now(UTC)
    try:
        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            display_name=display_name,
            role=UserRole.regular,
            is_active=True,
        )
        db.add(user)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise await _conflict()

    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    session = Session(
        user_id=user.id,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    db.add(session)
    await db.flush()

    record_login_attempt(db, email=email, ip=ip, success=True)
    user.last_login_at = now
    await write_audit(
        db,
        action="user.created",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        data={"email": email, "auth_method": "password"},
        ip_address=ip,
    )
    await db.commit()

    _set_session_cookie(response, session.id, expires_at)
    return LoginResponse(
        user=UserOut.model_validate(user), csrf_token=derive_csrf_token(session.id)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    auth.session.revoked_at = datetime.now(UTC)
    await write_audit(
        db,
        action="session.revoked",
        actor_id=auth.user.id,
        resource_type="session",
        resource_id=str(auth.session.id),
        ip_address=client_ip(request),
    )
    await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/csrf", response_model=CsrfResponse)
async def csrf_token(auth: AuthContext = Depends(get_current_auth)) -> CsrfResponse:
    return CsrfResponse(token=derive_csrf_token(auth.session.id))