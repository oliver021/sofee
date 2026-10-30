"""Admin de runs del agente: lista filtrable, detalle con su línea de tiempo, cancelación, valoraciones y uso.

Solo lectura salvo la cancelación, la revisión de valoraciones (ambas auditadas). El contenido de los
hilos se muestra porque el admin revisa la calidad de las respuestas; el resto de datos son metadatos.
"""

import base64
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import Row, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql.elements import ColumnElement

from ...agent.executor import ACTIVE_STATUSES, executor
from ...db import get_session
from ...models.agent import AgentProfile, AgentRun, AgentRunEvent
from ...models.feedback import MessageFeedback
from ...models.thread import Message
from ...models.user import User
from ...schemas.agent import RunEventOut
from ...schemas.agent_admin import (
    AdminFeedbackOut,
    AdminFeedbackPage,
    AdminRunDetailOut,
    AdminRunOut,
    AdminRunPage,
    FeedbackReviewIn,
    RunStatus,
    UsageOut,
)
from ...schemas.conversation import ComposerMode
from ...services.agent_usage import usage_report
from ...services.audit import write_audit
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(prefix="/admin", tags=["admin:agent-runs"], dependencies=[Depends(require_admin)])

DEFAULT_PAGE = 50
MAX_PAGE = 200

# Dos alias de `messages`: una para buscar la pregunta previa (subconsulta) y otra para leer su texto.
_QuestionAlias = aliased(Message)
_QuestionRow = aliased(Message)


# --- cursor (mismo patrón que /admin/audit, con uuid como desempate) ----------------------


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    payload = json.dumps({"t": created_at.isoformat(), "i": str(row_id)})
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
        return datetime.fromisoformat(payload["t"]), uuid.UUID(payload["i"])
    except Exception:  # noqa: BLE001 - cualquier cursor mal formado es un 400
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")


def _keyset(created_col: InstrumentedAttribute[datetime], id_col: InstrumentedAttribute[uuid.UUID], cursor: str | None) -> ColumnElement[bool] | None:
    if cursor is None:
        return None
    cursor_at, cursor_id = _decode_cursor(cursor)
    return or_(
        created_col < cursor_at,
        and_(created_col == cursor_at, id_col < cursor_id),
    )


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _duration_ms(run: AgentRun) -> int | None:
    if run.started_at is None or run.finished_at is None:
        return None
    return int((run.finished_at - run.started_at).total_seconds() * 1000)


def _run_out(run: AgentRun, email: str | None) -> AdminRunOut:
    return AdminRunOut(
        id=run.id,
        thread_id=run.thread_id,
        user_id=run.user_id,
        user_email=email,
        kind=run.kind,
        mode=run.mode,
        status=run.status,
        catalog_slug=run.catalog_slug,
        model_label=run.model_label,
        provider_model_id=run.provider_model_id,
        error_code=run.error_code,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        cost_estimate=_money(run.cost_estimate),
        ttft_ms=run.ttft_ms,
        duration_ms=_duration_ms(run),
        hallucinated_citations=run.hallucinated_citations,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def collapse_deltas(rows: Sequence[tuple[int, str, dict]]) -> list[RunEventOut]:
    """Todos los `message.delta` del run pasan a un único evento, en la posición del primero.

    `payload.text` es el texto completo que se vio; `chunks` cuenta los trozos originales.
    """
    events: list[RunEventOut] = []
    delta_at: int | None = None
    chunks: list[str] = []
    for seq, kind, payload in rows:
        if kind == "message.delta":
            if delta_at is None:
                delta_at = len(events)
                events.append(RunEventOut(seq=seq, type=kind, payload={}))
            chunks.append(str((payload or {}).get("text") or ""))
            continue
        events.append(RunEventOut(seq=seq, type=kind, payload=payload or {}))
    if delta_at is not None:
        first = events[delta_at]
        events[delta_at] = RunEventOut(
            seq=first.seq,
            type="message.delta",
            payload={"text": "".join(chunks), "chunks": len(chunks)},
        )
    return events


# --- runs ---------------------------------------------------------------------------------


@router.get("/runs", response_model=AdminRunPage)
async def list_runs(
    limit: int = Query(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    cursor: str | None = None,
    user: str | None = Query(default=None, max_length=200, description="UUID del usuario, o parte del email o del nombre"),
    mode: ComposerMode | None = None,
    run_status: RunStatus | None = Query(default=None, alias="status"),
    catalog_slug: str | None = Query(default=None, max_length=200),
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_session),
) -> AdminRunPage:
    stmt = select(AgentRun, User.email).join(User, User.id == AgentRun.user_id)
    conditions = []
    if user:
        try:
            conditions.append(AgentRun.user_id == uuid.UUID(user))
        except ValueError:
            conditions.append(
                or_(
                    User.email.icontains(user, autoescape=True),
                    User.display_name.icontains(user, autoescape=True),
                )
            )
    if mode is not None:
        conditions.append(AgentRun.mode == mode)
    if run_status is not None:
        conditions.append(AgentRun.status == run_status)
    if catalog_slug:
        conditions.append(AgentRun.catalog_slug == catalog_slug)
    if start is not None:
        conditions.append(AgentRun.created_at >= start)
    if end is not None:
        conditions.append(AgentRun.created_at <= end)
    keyset = _keyset(AgentRun.created_at, AgentRun.id, cursor)
    if keyset is not None:
        conditions.append(keyset)
    if conditions:
        stmt = stmt.where(*conditions)

    rows = (
        await db.execute(stmt.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1][0].created_at, page[-1][0].id) if has_more and page else None
    return AdminRunPage(items=[_run_out(run, email) for run, email in page], next_cursor=next_cursor)


@router.get("/runs/{run_id}", response_model=AdminRunDetailOut)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_session)) -> AdminRunDetailOut:
    row = (
        await db.execute(
            select(AgentRun, User.email).join(User, User.id == AgentRun.user_id).where(AgentRun.id == run_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run, email = row

    question = await db.get(Message, run.user_message_id) if run.user_message_id else None
    answer = await db.get(Message, run.assistant_message_id)
    profile = await db.get(AgentProfile, run.profile_version_id) if run.profile_version_id else None
    event_rows = (
        await db.execute(
            select(AgentRunEvent.seq, AgentRunEvent.type, AgentRunEvent.payload)
            .where(AgentRunEvent.run_id == run.id)
            .order_by(AgentRunEvent.seq.asc())
        )
    ).all()

    base = _run_out(run, email)
    return AdminRunDetailOut(
        **base.model_dump(),
        question=question.text if question is not None else None,
        answer=answer.text if answer is not None else None,
        citations=answer.citations if answer is not None else None,
        error_message=run.error_message,
        profile_version_id=run.profile_version_id,
        profile_version=profile.version if profile is not None else None,
        trace_url=run.trace_url,
        events=collapse_deltas([(seq, kind, payload) for seq, kind, payload in event_rows]),
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Cancela cualquier run, no solo los del admin. Idempotente: un run terminado solo se ignora."""
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in ACTIVE_STATUSES:
        await write_audit(
            db,
            action="agent.run_cancelled",
            actor_id=auth.user.id,
            resource_type="agent_run",
            resource_id=str(run.id),
            data={"thread_id": str(run.thread_id), "previous_status": run.status, "scope": "admin"},
            ip_address=client_ip(request),
        )
        await db.commit()
    await executor.cancel(str(run.id))
    return Response(status_code=status.HTTP_202_ACCEPTED)


# --- valoraciones -------------------------------------------------------------------------


def _feedback_query() -> Select:
    """Valoración + respuesta + pregunta previa + último run de esa respuesta, en una sola consulta."""
    question_seq = (
        select(func.max(_QuestionAlias.seq))
        .where(
            _QuestionAlias.thread_id == Message.thread_id,
            _QuestionAlias.role == "user",
            _QuestionAlias.seq < Message.seq,
        )
        .correlate(Message)
        .scalar_subquery()
    )
    latest_run = (
        select(AgentRun.id)
        .where(AgentRun.assistant_message_id == Message.id)
        .order_by(AgentRun.created_at.desc())
        .limit(1)
        .correlate(Message)
        .scalar_subquery()
    )
    return (
        select(MessageFeedback, Message.text, Message.thread_id, User.email, _QuestionRow.text, latest_run)
        .join(Message, Message.id == MessageFeedback.message_id)
        .join(User, User.id == MessageFeedback.user_id)
        .outerjoin(
            _QuestionRow,
            and_(
                _QuestionRow.thread_id == Message.thread_id,
                _QuestionRow.role == "user",
                _QuestionRow.seq == question_seq,
            ),
        )
    )


def _feedback_out(row: Row) -> AdminFeedbackOut:
    feedback, answer, thread_id, email, question, run_id = row
    return AdminFeedbackOut(
        id=feedback.id,
        value=feedback.value,
        reason=feedback.reason,
        comment=feedback.comment,
        reviewed=feedback.reviewed_at is not None,
        reviewed_at=feedback.reviewed_at,
        created_at=feedback.created_at,
        user_email=email,
        thread_id=thread_id,
        message_id=feedback.message_id,
        run_id=run_id,
        question=question,
        answer=answer,
    )


@router.get("/feedback", response_model=AdminFeedbackPage)
async def list_feedback(
    limit: int = Query(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    cursor: str | None = None,
    value: str | None = Query(default=None, pattern="^(good|bad)$"),
    reviewed: bool | None = None,
    db: AsyncSession = Depends(get_session),
) -> AdminFeedbackPage:
    stmt = _feedback_query()
    conditions = []
    if value is not None:
        conditions.append(MessageFeedback.value == value)
    if reviewed is not None:
        conditions.append(
            MessageFeedback.reviewed_at.is_not(None) if reviewed else MessageFeedback.reviewed_at.is_(None)
        )
    keyset = _keyset(MessageFeedback.created_at, MessageFeedback.id, cursor)
    if keyset is not None:
        conditions.append(keyset)
    if conditions:
        stmt = stmt.where(*conditions)

    rows = (
        await db.execute(stmt.order_by(MessageFeedback.created_at.desc(), MessageFeedback.id.desc()).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1][0].created_at, page[-1][0].id) if has_more and page else None
    return AdminFeedbackPage(items=[_feedback_out(row) for row in page], next_cursor=next_cursor)


@router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackOut)
async def review_feedback(
    feedback_id: uuid.UUID,
    payload: FeedbackReviewIn,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> AdminFeedbackOut:
    feedback = await db.get(MessageFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    feedback.reviewed_at = datetime.now(UTC) if payload.reviewed else None
    await write_audit(
        db,
        action="agent.feedback_reviewed",
        actor_id=auth.user.id,
        resource_type="message_feedback",
        resource_id=str(feedback.id),
        data={"reviewed": payload.reviewed, "value": feedback.value},
        ip_address=client_ip(request),
    )
    await db.commit()
    row = (await db.execute(_feedback_query().where(MessageFeedback.id == feedback_id))).one()
    return _feedback_out(row)


# --- uso ----------------------------------------------------------------------------------


@router.get("/usage", response_model=UsageOut)
async def get_usage(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> UsageOut:
    return await usage_report(db, days=days)


__all__ = ["collapse_deltas", "router"]
