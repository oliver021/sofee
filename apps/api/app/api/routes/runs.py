"""Endpoints del agente: runs, SSE, cancelación, revisión del plan, valoraciones, contexto y archivos.

Contrato v1 en docs/deep-agent-roadmap.md §3.7 y §3.10. Todas las mutaciones exigen
X-CSRF-Token. Los recursos de otro usuario responden 404, como en `conversations.py`.
"""

import json
import logging
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.events import text_of
from ...agent.executor import ACTIVE_STATUSES, StoredEvent, executor
from ...agent.history import load_compaction_input, summary_request
from ...agent.models import ModelUnavailable
from ...agent.persistence import get_agent_storage
from ...db import get_session
from ...models.agent import AgentRun, AgentRunEvent
from ...models.feedback import MessageFeedback
from ...models.thread import Message, Thread
from ...schemas.agent import (
    ClearOut,
    CompactOut,
    FeedbackIn,
    FileContentOut,
    FileOut,
    RunCreate,
    RunCreated,
    RunEventOut,
    RunOut,
    RunResume,
    RunSummaryOut,
    StarterOut,
)
from ...schemas.conversation import ComposerMode
from ...services.app_settings import agent_enabled, role_quota, starters
from ...services.audit import write_audit
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth
from .conversations import has_active_run, is_server_owned

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# Latido del SSE. Un test lo baja para no esperar 15 s.
HEARTBEAT_SECONDS = 15.0
_EVENT_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_NOTES_PREFIX = "/notes/"


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


async def _owned_thread(
    db: AsyncSession, owner_id: uuid.UUID, client_id: str, *, lock: bool = False
) -> Thread:
    query = select(Thread).where(Thread.owner_id == owner_id, Thread.client_id == client_id)
    if lock:
        # Serializa dos POST /runs del mismo hilo: el segundo ve el run activo del primero.
        query = query.with_for_update()
    thread = (await db.execute(query)).scalar_one_or_none()
    if thread is None:
        raise _not_found("Thread not found")
    return thread


async def _owned_run(db: AsyncSession, owner_id: uuid.UUID, run_id: str) -> AgentRun:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise _not_found("Run not found") from None
    run = (
        await db.execute(
            select(AgentRun).where(AgentRun.id == run_uuid, AgentRun.user_id == owner_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise _not_found("Run not found")
    return run


async def _message_by_client(db: AsyncSession, thread: Thread, client_id: str) -> Message | None:
    return (
        await db.execute(
            select(Message).where(Message.thread_id == thread.id, Message.client_id == client_id)
        )
    ).scalar_one_or_none()


async def _preceding_user_message(
    db: AsyncSession, thread: Thread, assistant_seq: int
) -> Message | None:
    return (
        await db.execute(
            select(Message)
            .where(
                Message.thread_id == thread.id,
                Message.role == "user",
                Message.seq < assistant_seq,
            )
            .order_by(Message.seq.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _quota_reset(db: AsyncSession, user_id: uuid.UUID, role: str) -> str | None:
    """Hora de reinicio (medianoche UTC) si el usuario superó su cuota del día; si no, None."""
    limits = await role_quota(db, role)
    runs_limit = limits.get("runs_per_day")
    tokens_limit = limits.get("tokens_per_day")
    if runs_limit is None and tokens_limit is None:
        return None
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    runs, tokens = (
        await db.execute(
            select(
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0),
            ).where(AgentRun.user_id == user_id, AgentRun.created_at >= start)
        )
    ).one()
    exceeded = (runs_limit is not None and runs >= runs_limit) or (
        tokens_limit is not None and int(tokens) >= tokens_limit
    )
    return (start + timedelta(days=1)).isoformat() if exceeded else None


# --- runs -----------------------------------------------------------------------------------


@router.post("/threads/{thread_id}/runs", response_model=RunCreated, status_code=201)
async def create_run(
    thread_id: str,
    payload: RunCreate,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> RunCreated | JSONResponse:
    """Crea el run y los mensajes que le tocan, y lo lanza en segundo plano."""
    incoming = payload.user_message
    if payload.kind == "send" and incoming is None:
        raise HTTPException(status_code=422, detail="user_message is required for send")

    thread = await _owned_thread(db, auth.user.id, thread_id, lock=True)
    if not await agent_enabled(db):
        raise HTTPException(status_code=503, detail="agent_disabled")
    if await has_active_run(db, thread.id):
        raise HTTPException(status_code=409, detail="run_active")
    reset_at = await _quota_reset(db, auth.user.id, auth.user.role.value)
    if reset_at is not None:
        return JSONResponse(
            status_code=429, content={"detail": "quota_exceeded", "reset_at": reset_at}
        )

    thread.updated_at = datetime.now(UTC)
    if payload.kind == "send" and incoming is not None:
        user_message = await _message_by_client(db, thread, incoming.client_id)
        if user_message is None:
            user_message = Message(
                thread_id=thread.id,
                client_id=incoming.client_id,
                role="user",
                text=incoming.text,
                status="complete",
                attachment_ids=incoming.attachment_ids,
            )
            db.add(user_message)
            await db.flush()

        assistant = await _message_by_client(db, thread, payload.assistant_client_id)
        if assistant is None:
            assistant = Message(
                thread_id=thread.id,
                client_id=payload.assistant_client_id,
                role="assistant",
                text="",
                status="pending",
            )
            db.add(assistant)
            await db.flush()
        else:
            if assistant.role != "assistant":
                raise HTTPException(status_code=409, detail="client_id_conflict")
            if await is_server_owned(db, assistant.id):
                raise HTTPException(status_code=409, detail="server_owned")
            assistant.text = ""
            assistant.status = "pending"
            assistant.citations = None
    else:
        assistant = await _message_by_client(db, thread, payload.assistant_client_id)
        if assistant is None or assistant.role != "assistant":
            raise _not_found("Message not found")
        if payload.kind == "continue" and assistant.status != "stopped":
            raise HTTPException(status_code=409, detail="not_stopped")
        user_message = await _preceding_user_message(db, thread, assistant.seq)
        if user_message is None:
            raise HTTPException(status_code=409, detail="no_user_message")
        if payload.kind == "regenerate":
            assistant.text = ""
            assistant.citations = None
        assistant.status = "pending"

    run = AgentRun(
        thread_id=thread.id,
        user_id=auth.user.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant.id,
        kind=payload.kind,
        mode=payload.mode,
        catalog_slug=payload.model_slug,
        status="queued",
    )
    db.add(run)
    await db.flush()
    run_id = str(run.id)
    await db.commit()

    executor.start(run_id)
    return RunCreated(run_id=run_id, assistant_message_id=payload.assistant_client_id, status="queued")


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE de un run: replay desde `after` (o `Last-Event-ID`) y después los eventos en vivo."""
    run = await _owned_run(db, auth.user.id, run_id)
    start_after = after
    last_event_id = request.headers.get("last-event-id", "")
    if last_event_id.isdigit():
        start_after = int(last_event_id)
    # La sesión de la petición vive hasta que el stream termina; sin cerrarla, cada SSE abierto
    # retendría una conexión del pool (idle in transaction) durante todo el run.
    await db.close()
    events = executor.stream(str(run.id), start_after, heartbeat=HEARTBEAT_SECONDS)
    return StreamingResponse(
        _frames(events), media_type="text/event-stream", headers=_EVENT_STREAM_HEADERS
    )


async def _frames(events: AsyncGenerator[StoredEvent | None]) -> AsyncIterator[bytes]:
    try:
        async for event in events:
            if event is None:
                yield b": ping\n\n"
                continue
            data = json.dumps(event.payload, ensure_ascii=False, default=str)
            yield f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n".encode()
    finally:
        await events.aclose()


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> Response:
    run = await _owned_run(db, auth.user.id, run_id)
    if run.status in ACTIVE_STATUSES:
        await write_audit(
            db,
            action="agent.run_cancelled",
            actor_id=auth.user.id,
            resource_type="agent_run",
            resource_id=str(run.id),
            data={"thread_id": str(run.thread_id), "previous_status": run.status},
            ip_address=client_ip(request),
        )
        await db.commit()
    # Un run ya terminado no es un error: la cancelación es idempotente.
    await executor.cancel(str(run.id))
    return Response(status_code=202)


@router.post("/runs/{run_id}/resume", status_code=202)
async def resume_run(
    run_id: str,
    payload: RunResume,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Responde a la revisión del plan: aprobar, editar los pasos o rechazarlo."""
    run = await _owned_run(db, auth.user.id, run_id)
    if payload.decision == "edit" and not payload.todos:
        raise HTTPException(status_code=422, detail="todos are required for edit")
    if not await agent_enabled(db):
        raise HTTPException(status_code=503, detail="agent_disabled")
    if run.status != "interrupted":
        raise HTTPException(status_code=409, detail="not_interrupted")
    todos = [todo.model_dump() for todo in payload.todos] if payload.todos is not None else None
    if not await executor.resume(str(run.id), payload.decision, todos):
        raise HTTPException(status_code=409, detail="not_interrupted")
    return Response(status_code=202)


@router.get("/threads/{thread_id}/runs", response_model=list[RunOut])
async def list_thread_runs(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> list[RunOut]:
    """Runs del hilo, del más antiguo al más nuevo, con sus eventos salvo `message.delta`."""
    thread = await _owned_thread(db, auth.user.id, thread_id)
    rows = (
        await db.execute(
            select(AgentRun, Message.client_id)
            .join(Message, Message.id == AgentRun.assistant_message_id)
            .where(AgentRun.thread_id == thread.id)
            .order_by(AgentRun.created_at.asc())
        )
    ).all()
    events_by_run: dict[uuid.UUID, list[RunEventOut]] = defaultdict(list)
    if rows:
        event_rows = (
            await db.execute(
                select(AgentRunEvent.run_id, AgentRunEvent.seq, AgentRunEvent.type, AgentRunEvent.payload)
                .where(
                    AgentRunEvent.run_id.in_([run.id for run, _ in rows]),
                    AgentRunEvent.type != "message.delta",
                )
                .order_by(AgentRunEvent.run_id, AgentRunEvent.seq.asc())
            )
        ).all()
        for run_pk, seq, kind, payload in event_rows:
            events_by_run[run_pk].append(RunEventOut(seq=seq, type=kind, payload=payload))
    return [
        RunOut(
            run_id=str(run.id),
            assistant_message_id=client_id,
            status=run.status,
            mode=run.mode,
            started_at=run.started_at,
            finished_at=run.finished_at,
            events=events_by_run.get(run.id, []),
        )
        for run, client_id in rows
    ]


@router.get(
    "/threads/{thread_id}/runs/latest",
    response_model=RunSummaryOut,
    responses={204: {"description": "El hilo no tiene ningún run."}},
)
async def latest_thread_run(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> RunSummaryOut | Response:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    row = (
        await db.execute(
            select(AgentRun, Message.client_id)
            .join(Message, Message.id == AgentRun.assistant_message_id)
            .where(AgentRun.thread_id == thread.id)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return Response(status_code=204)
    run, client_id = row
    return RunSummaryOut(
        run_id=str(run.id),
        assistant_message_id=client_id,
        status=run.status,
        mode=run.mode,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


# --- valoraciones -----------------------------------------------------------------------


@router.put("/threads/{thread_id}/messages/{message_id}/feedback", status_code=204)
async def put_message_feedback(
    thread_id: str,
    message_id: str,
    payload: FeedbackIn,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Valora una respuesta del asistente. `value: null` retira la valoración."""
    thread = await _owned_thread(db, auth.user.id, thread_id)
    message = await _message_by_client(db, thread, message_id)
    if message is None:
        raise _not_found("Message not found")
    if message.role != "assistant":
        raise HTTPException(status_code=422, detail="Only assistant messages can be rated")

    existing = (
        await db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message.id,
                MessageFeedback.user_id == auth.user.id,
            )
        )
    ).scalar_one_or_none()
    if payload.value is None:
        if existing is not None:
            await db.delete(existing)
    elif existing is None:
        db.add(
            MessageFeedback(
                message_id=message.id,
                user_id=auth.user.id,
                value=payload.value,
                reason=payload.reason,
                comment=payload.comment,
            )
        )
    else:
        existing.value = payload.value
        existing.reason = payload.reason
        existing.comment = payload.comment
        existing.reviewed_at = None
    await db.commit()
    return Response(status_code=204)


# --- contexto ---------------------------------------------------------------------------


@router.post("/threads/{thread_id}/context/compact", response_model=CompactOut)
async def compact_thread_context(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CompactOut | JSONResponse:
    """Resume los turnos vigentes con el modelo y guarda el resumen con su corte."""
    thread = await _owned_thread(db, auth.user.id, thread_id)
    compaction = await load_compaction_input(db, thread)
    if not compaction.turns:
        return CompactOut(summary_through_seq=thread.summary_through_seq)
    try:
        resolved = await executor.model_resolver(db, None)
    except ModelUnavailable:
        return JSONResponse(status_code=503, content={"detail": "model_unavailable"})
    try:
        reply = await resolved.chat_model.ainvoke(summary_request(compaction))
    except Exception:  # noqa: BLE001 - cualquier fallo del proveedor se devuelve como 502
        logger.warning("Compactar el hilo %s falló en el proveedor", thread_id)
        return JSONResponse(status_code=502, content={"detail": "summary_failed"})
    summary = text_of(reply.content).strip()
    if not summary:
        return JSONResponse(status_code=502, content={"detail": "summary_failed"})

    thread.summary = summary
    thread.summary_through_seq = compaction.through_seq
    await db.commit()
    return CompactOut(summary_through_seq=thread.summary_through_seq)


@router.post("/threads/{thread_id}/context/clear", response_model=ClearOut)
async def clear_thread_context(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ClearOut:
    """Deja de enviar al modelo todo lo anterior. Los mensajes siguen visibles en el hilo."""
    thread = await _owned_thread(db, auth.user.id, thread_id)
    last_seq = (
        await db.execute(select(func.max(Message.seq)).where(Message.thread_id == thread.id))
    ).scalar_one()
    thread.context_start_seq = (last_seq or 0) + 1
    await db.commit()
    return ClearOut(context_start_seq=thread.context_start_seq)


# --- arranque y archivos ----------------------------------------------------------------


@router.get("/starters", response_model=list[StarterOut])
async def list_starters(
    mode: ComposerMode = Query(...),
    locale: str = Query(default="es", min_length=2, max_length=10),
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> list[StarterOut]:
    """Preguntas de arranque del admin para un modo. Lista vacía: el cliente usa las suyas."""
    return [StarterOut(text=text) for text in await starters(db, mode, locale)]


@router.get("/threads/{thread_id}/files", response_model=list[FileOut])
async def list_agent_files(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> list[FileOut]:
    """Archivos que el agente dejó en /notes/ de este hilo."""
    thread = await _owned_thread(db, auth.user.id, thread_id)
    store = get_agent_storage().store
    items = await store.asearch((str(thread.id), "notes"), limit=500)
    return [
        FileOut(
            path=f"/notes{item.key}",
            size=len(str(item.value.get("content", "")).encode("utf-8")),
            updated_at=item.updated_at.isoformat(),
        )
        for item in items
    ]


@router.get("/threads/{thread_id}/files/content", response_model=FileContentOut)
async def read_agent_file(
    thread_id: str,
    path: str = Query(..., max_length=512),
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> FileContentOut:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    if not path.startswith(_NOTES_PREFIX) or ".." in path:
        raise _not_found("File not found")
    item = await get_agent_storage().store.aget((str(thread.id), "notes"), path[len("/notes"):])
    if item is None:
        raise _not_found("File not found")
    return FileContentOut(path=path, content=str(item.value.get("content", "")))


__all__ = ["HEARTBEAT_SECONDS", "router"]
