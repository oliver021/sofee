import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.session import Session
from ...models.user import User
from ...schemas import SessionOut, UserOut, UserUpdate
from ...services.audit import write_audit
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[UserOut])
async def list_users(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    stmt = select(User)
    if q:
        stmt = stmt.where(
            or_(User.email.ilike(f"%{q}%"), User.display_name.ilike(f"%{q}%"))
        )
    rows = (
        await db.execute(
            stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars()
    return [UserOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> UserOut:
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if auth.user.id == target.id:
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account",
            )
        if payload.role is not None and payload.role is not target.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role",
            )

    if payload.role is not None and payload.role is not target.role:
        previous = target.role
        target.role = payload.role
        await write_audit(
            db,
            action="user.role_changed",
            actor_id=auth.user.id,
            resource_type="user",
            resource_id=str(target.id),
            data={
                "email": target.email,
                "from": previous.value,
                "to": target.role.value,
            },
            ip_address=client_ip(request),
        )

    if payload.is_active is not None and payload.is_active is not target.is_active:
        target.is_active = payload.is_active
        await write_audit(
            db,
            action="user.deactivated" if not target.is_active else "user.activated",
            actor_id=auth.user.id,
            resource_type="user",
            resource_id=str(target.id),
            data={"email": target.email},
            ip_address=client_ip(request),
        )

    await db.commit()
    await db.refresh(target)
    return UserOut.model_validate(target)


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users/{user_id}/sessions", response_model=list[SessionOut])
async def list_user_sessions(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    await _load_user(db, user_id)
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .order_by(Session.created_at.desc())
        )
    ).scalars()
    return [SessionOut.model_validate(s) for s in rows if s.expires_at > now]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_any_session(
    session_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    session = (
        await db.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    if session.id == auth.session.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own current session",
        )
    session.revoked_at = datetime.now(UTC)
    await write_audit(
        db,
        action="session.revoked",
        actor_id=auth.user.id,
        resource_type="session",
        resource_id=str(session.id),
        data={"target_user_id": str(session.user_id)},
        ip_address=client_ip(request),
    )
    await db.commit()


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_sessions(
    user_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    target = await _load_user(db, user_id)
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        )
    ).scalars()
    count = 0
    for session in rows:
        if auth.user.id == target.id and session.id == auth.session.id:
            continue
        session.revoked_at = now
        count += 1
    await write_audit(
        db,
        action="user.sessions_revoked",
        actor_id=auth.user.id,
        resource_type="user",
        resource_id=str(target.id),
        data={"email": target.email, "count": count},
        ip_address=client_ip(request),
    )
    await db.commit()