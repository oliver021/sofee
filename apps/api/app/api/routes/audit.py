import base64
import json
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_session
from ...models.audit import AuditLog
from ...schemas.audit import AuditEntryOut, AuditPage
from ..deps import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin:audit"],
    dependencies=[Depends(require_admin)],
)


def _encode_cursor(created_at: datetime, entry_id: int) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "i": entry_id})
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
        created_at = datetime.fromisoformat(payload["t"])
        return created_at, int(payload["i"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def _serialize(entry: AuditLog) -> AuditEntryOut:
    return AuditEntryOut(
        id=entry.id,
        actor_id=entry.actor_id,
        actor_email=entry.actor.email if entry.actor is not None else None,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        metadata=entry.data,
        ip_address=entry.ip_address,
        created_at=entry.created_at,
    )


@router.get("/audit", response_model=AuditPage)
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_session),
) -> AuditPage:
    stmt = select(AuditLog).options(selectinload(AuditLog.actor))

    conditions: list = []
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)
    if action is not None:
        conditions.append(AuditLog.action == action)
    if resource_type is not None:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        conditions.append(AuditLog.resource_id == resource_id)
    if start is not None:
        conditions.append(AuditLog.created_at >= start)
    if end is not None:
        conditions.append(AuditLog.created_at <= end)
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                AuditLog.created_at < cursor_created_at,
                and_(
                    AuditLog.created_at == cursor_created_at,
                    AuditLog.id < cursor_id,
                ),
            )
        )
    if conditions:
        stmt = stmt.where(*conditions)

    rows = (
        (
            await db.execute(
                stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )

    has_more = len(rows) > limit
    page = rows[:limit]
    items = [_serialize(entry) for entry in page]
    next_cursor = (
        _encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    )
    return AuditPage(items=items, next_cursor=next_cursor)