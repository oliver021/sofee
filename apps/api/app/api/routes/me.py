from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.session import Session
from ...schemas import SessionOut, UserOut
from ...services.audit import write_audit
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
async def me(auth: AuthContext = Depends(get_current_auth)) -> UserOut:
    return UserOut.model_validate(auth.user)


@router.get("/me/sessions", response_model=list[SessionOut])
async def list_sessions(
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(Session)
            .where(Session.user_id == auth.user.id, Session.revoked_at.is_(None))
            .order_by(Session.created_at.desc())
        )
    ).scalars()
    return [SessionOut.model_validate(s) for s in rows if s.expires_at > now]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    _csrf=Depends(check_csrf),
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> None:
    session = (
        await db.execute(
            select(Session).where(
                Session.id == session_id, Session.user_id == auth.user.id
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.revoked_at = datetime.now(UTC)
    await write_audit(
        db,
        action="session.revoked",
        actor_id=auth.user.id,
        resource_type="session",
        resource_id=str(session_id),
        ip_address=client_ip(request),
    )
    await db.commit()