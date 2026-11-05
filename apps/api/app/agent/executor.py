"""Ejecución de runs: tareas en segundo plano, persistencia de eventos y difusión.

Cada run es una tarea asyncio que no depende de la petición HTTP que la creó: si se cierra
la pestaña, el run sigue, y el cliente recupera lo perdido con `Last-Event-ID`. Cada evento
se guarda en `agent_run_events` (con su `seq`) antes de difundirse a los suscriptores. Así
un suscriptor que se conecta tarde lee de la BD y luego escucha en vivo sin huecos ni duplicados.

Una revisión del plan (`interrupt`) termina la tarea y deja el run en `interrupted`; la
reanudación crea otra tarea con el mismo `thread_id` (el run) en el checkpointer.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import openai
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.errors import GraphRecursionError
from langgraph.store.base import BaseStore
from langgraph.types import Command
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import async_session_factory
from ..models.agent import AgentRun, AgentRunEvent
from ..models.thread import Message, Thread
from ..services.audit import write_audit
from ..services.integrations import TAVILY, is_configured
from .backends import make_backend
from .context import SofeeContext
from .events import TERMINAL_EVENTS, RunEventMapper, SofeeEvent
from .history import load_model_input
from .knowledge import prepare_run_knowledge
from .leaked_calls import recover_leaked_ui_calls
from .limits import TASK_TOOL
from .models import ModelUnavailable, ResolvedModel, resolve_chat_model
from .persistence import get_agent_storage
from .profiles import ProfileSpec, build_agent, load_profile
from .replay import Recording, find_recording, pacing, rebase_payload
from .sources import finalize, get_registry, release_registry
from .tools import get_tools
from .tools.search import SEARCH_TOOL_NAMES

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "es"
DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_SECONDS = 300.0
# Un texto parcial se persiste como mucho cada segundo; al pausar o terminar siempre se escribe.
TEXT_FLUSH_SECONDS = 1.0
ACTIVE_STATUSES = ("queued", "running", "interrupted")
_NOTES_ROUTE = "/notes"

ModelResolver = Callable[[AsyncSession, str | None], Awaitable[ResolvedModel]]


async def _default_model_resolver(db: AsyncSession, slug: str | None) -> ResolvedModel:
    return await resolve_chat_model(db, slug)


@dataclass(frozen=True)
class StoredEvent:
    seq: int
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class _Resume:
    decision: str
    todos: list[dict[str, str]] | None


@dataclass(eq=False)
class _RunState:
    """Estado de un run mientras una tarea lo ejecuta (o de uno pausado, al cancelarlo)."""

    run_id: str
    resume: _Resume | None = None
    loaded: bool = False
    started: bool = False
    finalizing: bool = False
    cancel_requested: bool = False
    interrupt_pending: bool = False
    status: str = "queued"
    kind: str = "send"
    mode: str = "learn"
    user_id: uuid.UUID | None = None
    thread_id: uuid.UUID | None = None
    user_message_id: uuid.UUID | None = None
    assistant_id: uuid.UUID | None = None
    assistant_client_id: str = ""
    assistant_status: str = "pending"
    catalog_slug: str | None = None
    text: str = ""
    seq: int = 0
    base_tokens: tuple[int, int] = (0, 0)
    usage: UsageMetadataCallbackHandler | None = None
    price: tuple[Decimal | None, Decimal | None] = (None, None)
    ttft_ms: int | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    last_flush: float = 0.0


class RunExecutor:
    """Ejecuta, reanuda y cancela runs; difunde sus eventos a los suscriptores."""

    def __init__(self) -> None:
        # Inyectable: los tests devuelven modelos falsos (sin red).
        self.model_resolver: ModelResolver = _default_model_resolver
        self._states: dict[str, _RunState] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[StoredEvent | None]]] = {}

    # --- API ----------------------------------------------------------------------------

    def start(self, run_id: str) -> None:
        """Lanza el run en segundo plano. El run ya debe estar confirmado en la BD."""
        self._spawn(run_id, resume=None)

    async def resume(self, run_id: str, decision: str, todos: list[dict[str, str]] | None) -> bool:
        """Reanuda un run `interrupted`. False si no estaba pausado (otra petición lo reclamó antes)."""
        previous = self._tasks.get(run_id)
        if previous is not None and not previous.done():
            # La tarea que pausó el run termina enseguida; esperar evita dos tareas a la vez.
            await asyncio.wait([previous])
        if not await _claim_resume(run_id):
            return False
        self._spawn(run_id, resume=_Resume(decision=decision, todos=todos))
        return True

    async def cancel(self, run_id: str) -> None:
        """Detiene el run. El texto parcial se conserva y el mensaje queda en `stopped`."""
        state = self._states.get(run_id)
        task = self._tasks.get(run_id)
        if state is not None and task is not None and not task.done():
            if state.finalizing:
                return
            state.cancel_requested = True
            if state.started:
                task.cancel()
            return
        # Sin tarea viva: el run está pausado esperando revisión, o ya terminó (no hace nada).
        await self._settle_cancelled(_RunState(run_id=run_id))

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is not None:
            await asyncio.wait([task])

    async def stream(
        self, run_id: str, after: int, *, heartbeat: float
    ) -> AsyncIterator[StoredEvent | None]:
        """Eventos con `seq > after`: primero los persistidos y luego los vivos.

        Se suscribe antes de leer la BD, así que ningún evento se pierde entre ambas fuentes;
        los duplicados se descartan por `seq`. Cede `None` cada `heartbeat` segundos sin eventos.
        Termina tras un evento terminal o cuando el run se cierra.
        """
        queue: asyncio.Queue[StoredEvent | None] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        try:
            last = after
            for event in await _replay(run_id, after):
                last = event.seq
                yield event
                if event.type in TERMINAL_EVENTS:
                    return
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield None
                    continue
                if item is None:
                    return
                if item.seq <= last:
                    continue
                last = item.seq
                yield item
                if item.type in TERMINAL_EVENTS:
                    return
        finally:
            self._unsubscribe(run_id, queue)

    # --- tareas -------------------------------------------------------------------------

    def _spawn(self, run_id: str, resume: _Resume | None) -> None:
        state = _RunState(run_id=run_id, resume=resume)
        task = asyncio.get_running_loop().create_task(self._main(state), name=f"run-{run_id}")
        self._states[run_id] = state
        self._tasks[run_id] = task
        task.add_done_callback(lambda done: self._forget(run_id, state, done))

    def _forget(self, run_id: str, state: _RunState, task: asyncio.Task[None]) -> None:
        if self._tasks.get(run_id) is task:
            del self._tasks[run_id]
        if self._states.get(run_id) is state:
            del self._states[run_id]

    async def _main(self, state: _RunState) -> None:
        state.started = True
        try:
            if state.cancel_requested:
                await self._settle_cancelled(state)
                return
            await self._execute(state)
        except asyncio.CancelledError:
            if not state.cancel_requested:
                raise
            await self._settle_cancelled(state)
        except Exception as exc:  # noqa: BLE001 - todo fallo del run se traduce a run.failed
            code, message, retryable = _classify(exc)
            if code == "internal":
                logger.exception("Run %s: error interno del agente", state.run_id)
            else:
                logger.warning("Run %s terminó con %s", state.run_id, code)
            try:
                await self._settle_failed(state, code, message, retryable, exc)
            except Exception:  # noqa: BLE001
                logger.exception("No se pudo registrar el fallo del run %s", state.run_id)

    async def _execute(self, state: _RunState) -> None:
        await self._ensure_loaded(state)
        if state.status not in ("queued", "running"):
            return

        # Antes de resolver ningún modelo: el plan B tiene que funcionar aunque el provider esté caído.
        recording = await self._recording_for(state)
        if recording is not None:
            await self._replay(state, recording)
            return

        async with async_session_factory() as db:
            thread = await db.get(Thread, state.thread_id)
            user_message = (
                await db.get(Message, state.user_message_id) if state.user_message_id else None
            )
            if thread is None or user_message is None:
                raise LookupError(f"El run {state.run_id} no tiene hilo o mensaje de usuario")
            profile = await load_profile(db, state.mode)
            resolved = await self.model_resolver(db, state.catalog_slug)
            web_search_ready = await is_configured(db, TAVILY)
            model_input = None
            if state.resume is None:
                continue_text = (
                    state.text if state.kind == "continue" and state.text.strip() else None
                )
                model_input = await load_model_input(
                    db, thread, user_message, continue_text=continue_text
                )

        state.price = (resolved.input_price, resolved.output_price)
        if state.resume is None:
            if not await self._mark_running(state, profile, resolved):
                return
            await self._emit(
                state,
                "run.started",
                {
                    "run_id": state.run_id,
                    "assistant_message_id": state.assistant_client_id,
                    "mode": state.mode,
                    "model_label": resolved.label,
                },
            )

        storage = get_agent_storage()
        agent = build_agent(
            profile,
            resolved,
            get_tools(state.mode, profile.config, web_search=web_search_ready),
            make_backend(),
            storage.checkpointer,
            storage.store,
        )
        handler = UsageMetadataCallbackHandler()
        state.usage = handler
        ctx = SofeeContext(
            user_id=str(state.user_id),
            thread_id=str(state.thread_id),
            run_id=state.run_id,
            mode=state.mode,
            locale=DEFAULT_LOCALE,
        )
        await prepare_run_files(ctx, storage.store)

        limits = profile.config.get("limits") or {}
        config: dict[str, Any] = {
            "configurable": {"thread_id": state.run_id},
            "recursion_limit": int(limits.get("max_steps", DEFAULT_MAX_STEPS)),
            "callbacks": [handler],
        }
        if state.resume is None:
            inputs: Any = {"messages": model_input}
        else:
            inputs = await _resume_command(agent, config, state.resume)

        mapper = RunEventMapper(
            context_window=resolved.context_window,
            usage_totals=lambda: _total_tokens(state),
        )
        async with asyncio.timeout(float(limits.get("max_seconds", DEFAULT_MAX_SECONDS))):
            async for part in agent.astream(
                inputs,
                config,
                context=ctx,
                stream_mode=["messages", "updates", "custom"],
                subgraphs=True,
                version="v2",
            ):
                for event in mapper.map(part):
                    await self._handle(state, event)

        if state.interrupt_pending:
            await self._settle_interrupted(state)
            return
        await self._settle_completed(state)

    async def _handle(self, state: _RunState, event: SofeeEvent) -> None:
        if event.type == "message.delta":
            state.text += str(event.payload.get("text") or "")
            if state.ttft_ms is None:
                state.ttft_ms = int((time.monotonic() - state.started_monotonic) * 1000)
            if state.assistant_status != "streaming":
                await self._flush_text(state, status="streaming")
            elif time.monotonic() - state.last_flush >= TEXT_FLUSH_SECONDS:
                await self._flush_text(state)
        elif event.type == "interrupt":
            state.interrupt_pending = True
        elif event.type == "file.written" and event.payload.get("size") is None:
            event.payload["size"] = await self._note_size(state, str(event.payload.get("path") or ""))
        await self._emit(state, event.type, event.payload)

    # --- cierre -------------------------------------------------------------------------

    async def _settle_interrupted(self, state: _RunState) -> None:
        await self._flush_text(state)
        async with async_session_factory() as db:
            input_tokens, output_tokens = _total_tokens(state)
            await db.execute(
                update(AgentRun)
                .where(AgentRun.id == _uuid(state.run_id))
                .values(
                    status="interrupted",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            )
            await db.commit()
        state.status = "interrupted"

    async def _settle_completed(self, state: _RunState) -> None:
        state.finalizing = True
        # Un modelo pequeño puede escribir la llamada a una herramienta de UI como texto: se
        # recupera como el evento que habría emitido y se quita de la respuesta.
        answer, recovered = recover_leaked_ui_calls(state.text.strip())
        for event_type, payload in recovered:
            await self._emit(state, event_type, payload)
        text, citations, hallucinated = finalize(answer, get_registry(state.run_id))
        await self._settle(
            state,
            run_status="completed",
            message_status="complete",
            text=text,
            citations=citations,
            hallucinated=hallucinated,
            event_type="run.completed",
            payload={
                "assistant_message_id": state.assistant_client_id,
                "text": text,
                "citations": citations,
            },
        )

    async def _settle_cancelled(self, state: _RunState) -> None:
        state.finalizing = True
        await self._ensure_loaded(state)
        text, citations, hallucinated = finalize(state.text, get_registry(state.run_id))
        await self._settle(
            state,
            run_status="cancelled",
            message_status="stopped",
            text=text,
            citations=citations or None,
            hallucinated=hallucinated,
            event_type="run.cancelled",
            payload={"assistant_message_id": state.assistant_client_id, "text": text},
            expected=ACTIVE_STATUSES,
        )

    async def _settle_failed(
        self, state: _RunState, code: str, message: str, retryable: bool, exc: BaseException
    ) -> None:
        state.finalizing = True
        await self._ensure_loaded(state)
        await self._settle(
            state,
            run_status="failed",
            message_status="error",
            text=state.text,
            citations=None,
            hallucinated=None,
            event_type="run.failed",
            payload={"error_code": code, "message": message, "retryable": retryable},
            expected=ACTIVE_STATUSES,
            error_code=code,
            error_message=f"{type(exc).__name__}: {message}",
        )

    async def _settle(
        self,
        state: _RunState,
        *,
        run_status: str,
        message_status: str,
        text: str,
        citations: list[dict[str, Any]] | None,
        hallucinated: int | None,
        event_type: str,
        payload: dict[str, Any],
        expected: tuple[str, ...] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Cierra el run en la BD y emite su evento terminal. False si ya no estaba en `expected`."""
        input_tokens, output_tokens = _total_tokens(state)
        values: dict[str, Any] = {
            "status": run_status,
            "finished_at": datetime.now(UTC),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "ttft_ms": state.ttft_ms,
            "error_code": error_code,
            "error_message": error_message,
        }
        cost = _cost(input_tokens, output_tokens, state.price)
        if cost is not None:
            values["cost_estimate"] = cost
        if hallucinated is not None:
            values["hallucinated_citations"] = hallucinated

        statement = update(AgentRun).where(AgentRun.id == _uuid(state.run_id))
        if expected is not None:
            statement = statement.where(AgentRun.status.in_(expected))
        async with async_session_factory() as db:
            result = await db.execute(statement.values(**values))
            if result.rowcount == 0:
                # El run ya no estaba activo (p. ej., cancelación de un run terminado): no hay evento.
                await db.rollback()
                release_registry(state.run_id)
                return False
            await db.execute(
                update(Message)
                .where(Message.id == state.assistant_id)
                .values(status=message_status, text=text, citations=citations)
            )
            await db.commit()
        state.status = run_status
        state.text = text
        await self._emit(state, event_type, payload)
        self._close(state.run_id)
        return True

    def _close(self, run_id: str) -> None:
        release_registry(run_id)
        for queue in self._subscribers.pop(run_id, set()):
            queue.put_nowait(None)

    # --- persistencia y difusión -------------------------------------------------------

    async def _ensure_loaded(self, state: _RunState) -> None:
        """Carga en `state` lo que el run necesita y reconstruye su registro de fuentes."""
        if state.loaded:
            return
        async with async_session_factory() as db:
            run = await db.get(AgentRun, _uuid(state.run_id))
            if run is None:
                raise LookupError(f"El run {state.run_id} no existe")
            assistant = await db.get(Message, run.assistant_message_id)
            max_seq = (
                await db.execute(
                    select(func.max(AgentRunEvent.seq)).where(AgentRunEvent.run_id == run.id)
                )
            ).scalar_one()
            sources = (
                await db.execute(
                    select(AgentRunEvent.payload)
                    .where(AgentRunEvent.run_id == run.id, AgentRunEvent.type == "source.added")
                    .order_by(AgentRunEvent.seq.asc())
                )
            ).scalars().all()
            tool_calls = (
                await db.execute(
                    select(AgentRunEvent.payload["name"].astext)
                    .where(AgentRunEvent.run_id == run.id, AgentRunEvent.type == "tool.started")
                )
            ).scalars().all()

        state.status = run.status
        state.kind = run.kind
        state.mode = run.mode
        state.user_id = run.user_id
        state.thread_id = run.thread_id
        state.user_message_id = run.user_message_id
        state.assistant_id = run.assistant_message_id
        state.catalog_slug = run.catalog_slug
        state.base_tokens = (run.input_tokens or 0, run.output_tokens or 0)
        state.ttft_ms = run.ttft_ms
        state.seq = max_seq or 0
        if assistant is not None:
            state.assistant_client_id = assistant.client_id
            state.assistant_status = assistant.status
            state.text = assistant.text or ""

        # El registro de fuentes vive en memoria; se reconstruye en el mismo orden para que las
        # citas `[n]` ya escritas sigan apuntando a la fuente correcta tras reanudar o reiniciar.
        registry = get_registry(state.run_id)
        for payload in sources:
            registry.add(
                kind=payload.get("kind", "web"),
                title=str(payload.get("title") or ""),
                url=payload.get("url"),
                ref=payload.get("ref"),
            )
        # El presupuesto de búsquedas y subagentes cuenta cada intento (tool.started), así que se
        # reconstruye igual que las fuentes.
        registry.searches = sum(1 for name in tool_calls if name in SEARCH_TOOL_NAMES)
        registry.subagents = sum(1 for name in tool_calls if name == TASK_TOOL)
        state.loaded = True

    async def _recording_for(self, state: _RunState) -> Recording | None:
        """Run grabado que responde a este mensaje según `replay.map`, si lo hay (ver replay.py)."""
        if state.resume is not None or state.kind != "send" or state.user_message_id is None:
            return None
        async with async_session_factory() as db:
            message = await db.get(Message, state.user_message_id)
            if message is None:
                return None
            return await find_recording(db, message.text)

    async def _replay(self, state: _RunState, recording: Recording) -> None:
        """Reemite un run grabado con su ritmo original. Pasa por `_handle`, así que el texto,
        el hilo y las cancelaciones se comportan como en un run en vivo."""
        if not await self._mark_replay_running(state, recording):
            return
        for event, gap in zip(recording.events, pacing(recording.events), strict=True):
            if gap > 0:
                await asyncio.sleep(gap)
            if event.type == "interrupt":
                continue
            payload = rebase_payload(
                event.payload,
                run_id=state.run_id,
                assistant_id=state.assistant_client_id,
                mode=state.mode,
            )
            if event.type == "run.completed":
                await self._settle(
                    state,
                    run_status="completed",
                    message_status="complete",
                    text=str(payload.get("text") or ""),
                    citations=payload.get("citations"),
                    hallucinated=None,
                    event_type="run.completed",
                    payload=payload,
                )
                return
            await self._handle(state, SofeeEvent(event.type, payload))
        # `_recording_for` solo acepta grabaciones que terminan en run.completed; esto es un cinturón.
        await self._settle_completed(state)

    async def _mark_replay_running(self, state: _RunState, recording: Recording) -> bool:
        """Pasa a `running` sin perfil ni modelo, y deja auditoría de qué run se reprodujo."""
        async with async_session_factory() as db:
            result = await db.execute(
                update(AgentRun)
                .where(AgentRun.id == _uuid(state.run_id), AgentRun.status == "queued")
                .values(
                    status="running",
                    started_at=datetime.now(UTC),
                    model_label=recording.model_label,
                )
            )
            if result.rowcount == 0:
                await db.rollback()
                return False
            await write_audit(
                db,
                action="agent.run_replayed",
                actor_id=state.user_id,
                resource_type="agent_run",
                resource_id=state.run_id,
                data={"recorded_run_id": str(recording.run_id), "thread_id": str(state.thread_id)},
            )
            await db.commit()
        state.status = "running"
        return True

    async def _mark_running(self, state: _RunState, profile: ProfileSpec, resolved: ResolvedModel) -> bool:
        async with async_session_factory() as db:
            result = await db.execute(
                update(AgentRun)
                .where(AgentRun.id == _uuid(state.run_id), AgentRun.status == "queued")
                .values(
                    status="running",
                    started_at=datetime.now(UTC),
                    profile_version_id=profile.profile_version_id,
                    catalog_slug=resolved.catalog_slug,
                    provider_model_id=resolved.provider_model_id,
                    model_label=resolved.label,
                )
            )
            if result.rowcount == 0:
                await db.rollback()
                return False
            await db.commit()
        state.status = "running"
        state.catalog_slug = resolved.catalog_slug
        return True

    async def _flush_text(self, state: _RunState, status: str | None = None) -> None:
        values: dict[str, Any] = {"text": state.text}
        if status is not None:
            values["status"] = status
            state.assistant_status = status
        async with async_session_factory() as db:
            await db.execute(
                update(Message).where(Message.id == state.assistant_id).values(**values)
            )
            await db.commit()
        state.last_flush = time.monotonic()

    async def _emit(self, state: _RunState, event_type: str, payload: dict[str, Any]) -> None:
        """Persiste el evento y, ya confirmado, lo difunde a los suscriptores del run."""
        state.seq += 1
        seq = state.seq
        async with async_session_factory() as db:
            db.add(
                AgentRunEvent(
                    run_id=_uuid(state.run_id), seq=seq, type=event_type, payload=payload
                )
            )
            await db.commit()
        event = StoredEvent(seq=seq, type=event_type, payload=payload)
        for queue in self._subscribers.get(state.run_id, ()):
            queue.put_nowait(event)

    async def _note_size(self, state: _RunState, path: str) -> int:
        """Tamaño actual de un archivo de /notes/ (lo que `edit_file` no informa)."""
        store = get_agent_storage().store
        item = await store.aget((str(state.thread_id), "notes"), path[len(_NOTES_ROUTE):])
        if item is None:
            return 0
        return len(str(item.value.get("content", "")).encode("utf-8"))

    def _unsubscribe(self, run_id: str, queue: asyncio.Queue[StoredEvent | None]) -> None:
        queues = self._subscribers.get(run_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self._subscribers[run_id]


executor = RunExecutor()


async def prepare_run_files(run: SofeeContext, store: BaseStore) -> None:
    """Prepara los archivos del run antes de invocar al agente: `/kb/` y `/attachments/` (B2)."""
    await prepare_run_knowledge(run, store)


# --- auxiliares --------------------------------------------------------------------------


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def _replay(run_id: str, after: int) -> list[StoredEvent]:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(AgentRunEvent.seq, AgentRunEvent.type, AgentRunEvent.payload)
                .where(AgentRunEvent.run_id == _uuid(run_id), AgentRunEvent.seq > after)
                .order_by(AgentRunEvent.seq.asc())
            )
        ).all()
    return [StoredEvent(seq=seq, type=kind, payload=payload) for seq, kind, payload in rows]


async def _claim_resume(run_id: str) -> bool:
    """Pasa el run de `interrupted` a `running` en una sola sentencia. Atómico frente a dos peticiones."""
    async with async_session_factory() as db:
        result = await db.execute(
            update(AgentRun)
            .where(AgentRun.id == _uuid(run_id), AgentRun.status == "interrupted")
            .values(status="running")
            .returning(AgentRun.id)
        )
        claimed = result.first() is not None
        await db.commit()
    return claimed


async def _resume_command(agent: Any, config: dict[str, Any], resume: _Resume) -> Command:  # noqa: ANN401
    """Una decisión por cada acción pendiente del checkpoint, en orden."""
    snapshot = await agent.aget_state(config)
    actions: list[dict[str, Any]] = []
    for task in snapshot.tasks:
        for interrupt in task.interrupts:
            value = interrupt.value if isinstance(interrupt.value, dict) else {}
            actions.extend(value.get("action_requests") or [])
    if not actions:
        raise LookupError("No hay ninguna revisión pendiente en el checkpoint del run")

    decisions: list[dict[str, Any]] = []
    for action in actions:
        if resume.decision == "edit" and action.get("name") == "write_todos":
            decisions.append(
                {
                    "type": "edit",
                    "edited_action": {
                        "name": "write_todos",
                        "args": {"todos": resume.todos or []},
                    },
                }
            )
        elif resume.decision == "reject":
            decisions.append({"type": "reject", "message": "El usuario no aprobó este plan."})
        else:
            decisions.append({"type": "approve"})
    return Command(resume={"decisions": decisions})


def _classify(exc: BaseException) -> tuple[str, str, bool]:
    """Código de error del contrato, mensaje fijo y si conviene reintentar."""
    if isinstance(exc, ModelUnavailable):
        return "model_unavailable", "No usable model binding for the agent", False
    if isinstance(exc, GraphRecursionError):
        return "timeout", "The run reached its step limit", False
    if isinstance(exc, TimeoutError):
        return "timeout", "The run exceeded its time limit", True
    if isinstance(exc, openai.RateLimitError):
        return "rate_limited", "The provider rate-limited the request", True
    if isinstance(exc, (openai.APIError, httpx.HTTPError)):
        return "provider_error", "The provider request failed", True
    return "internal", "Unexpected error in the agent", False


def _add(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def _total_tokens(state: _RunState) -> tuple[int, int]:
    """Tokens del run: los de sus ejecuciones anteriores más los de la actual, subagentes incluidos."""
    if state.usage is None:
        return state.base_tokens
    totals = state.usage.usage_metadata
    current = (
        sum(int(item.get("input_tokens") or 0) for item in totals.values()),
        sum(int(item.get("output_tokens") or 0) for item in totals.values()),
    )
    return _add(state.base_tokens, current)


def _cost(
    input_tokens: int, output_tokens: int, price: tuple[Decimal | None, Decimal | None]
) -> Decimal | None:
    """Coste estimado. Los precios del catálogo son por millón de tokens."""
    input_price, output_price = price
    if input_price is None or output_price is None:
        return None
    total = Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price
    return (total / Decimal(1_000_000)).quantize(Decimal("0.000001"))


async def recover_orphaned_runs() -> int:
    """Cierra como fallidos los runs `queued` o `running` que quedaron sin proceso (reinicio).

    Un run en curso vive en una tarea de su proceso: si el proceso murió, nadie lo terminará y
    bloquearía el hilo (`run_active`). Los `interrupted` no se tocan: siguen reanudables desde
    el checkpointer. Supone una sola réplica, como la difusión del SSE (roadmap §3.7).
    """
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        orphans = (
            await db.execute(select(AgentRun).where(AgentRun.status.in_(("queued", "running"))))
        ).scalars().all()
        for run in orphans:
            max_seq = (
                await db.execute(select(func.max(AgentRunEvent.seq)).where(AgentRunEvent.run_id == run.id))
            ).scalar_one()
            db.add(
                AgentRunEvent(
                    run_id=run.id,
                    seq=(max_seq or 0) + 1,
                    type="run.failed",
                    payload={
                        "error_code": "internal",
                        "message": "The server restarted during the run",
                        "retryable": True,
                    },
                )
            )
            run.status = "failed"
            run.error_code = "internal"
            run.error_message = "RestartError: the server restarted during the run"
            run.finished_at = now
            await db.execute(
                update(Message).where(Message.id == run.assistant_message_id).values(status="error")
            )
        await db.commit()
    if orphans:
        logger.warning("Se cerraron %d runs que quedaron sin proceso", len(orphans))
    return len(orphans)


__all__ = [
    "ACTIVE_STATUSES",
    "DEFAULT_LOCALE",
    "ModelResolver",
    "RunExecutor",
    "StoredEvent",
    "executor",
    "prepare_run_files",
    "recover_orphaned_runs",
]
