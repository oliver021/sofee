"""Protocolo de eventos de Sofee (v1) y mapeo desde el stream de LangGraph.

`RunEventMapper` es el único sitio que entiende las partes de
`astream(version="v2", subgraphs=True, stream_mode=["messages", "updates", "custom"])`.
No hace E/S: recibe partes y devuelve `SofeeEvent`, así que se prueba con partes
sintéticas (docs/deep-agent-roadmap.md §3.7 y docs/deep-agent-api-notes.md §10).

`ns == ()` es el agente principal. Cualquier otro `ns` es un subagente: su nombre
sale de `lc_agent_name` (en los tokens) o de `AIMessage.name` (en las actualizaciones).
"""

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

# Tipos del contrato v1. Cualquier evento fuera de esta lista es un error de mapeo.
EVENT_TYPES = frozenset(
    {
        "run.started",
        "status",
        "message.delta",
        "todos.updated",
        "tool.started",
        "tool.finished",
        "subagent.started",
        "subagent.finished",
        "source.added",
        "file.written",
        "ui.directions",
        "ui.quiz",
        "interrupt",
        "usage",
        "run.completed",
        "run.failed",
        "run.cancelled",
    }
)
TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})
# Eventos del stream custom que se reenvían tal cual (sin el campo `type`).
CUSTOM_EVENTS = frozenset({"status", "source.added", "ui.directions", "ui.quiz"})
# Escrituras que se anuncian como `file.written` cuando van a /notes/.
WRITE_TOOLS = frozenset({"write_file", "edit_file"})
NOTES_PREFIX = "/notes/"
MAIN_AGENT = "main"
SUBAGENT_FALLBACK = "subagent"

_PREVIEW_CHARS = 200
_SUMMARY_CHARS = 1000
_TASK_CHARS = 500
_TODO_STATUSES = frozenset({"pending", "in_progress", "completed"})

UsageTotals = Callable[[], tuple[int, int]]


@dataclass(frozen=True)
class SofeeEvent:
    type: str
    payload: dict[str, Any]


@dataclass
class _PendingTool:
    name: str
    agent: str
    args: dict[str, Any]
    started_at: float


class RunEventMapper:
    """Traduce partes de LangGraph a eventos de Sofee. Guarda estado entre partes de un mismo run.

    `usage_totals` devuelve los tokens acumulados (entrada, salida) del run, incluidos los
    subagentes. Si no se pasa, el mapeador suma por su cuenta el `usage_metadata` de cada
    respuesta del modelo. `clock` existe para que los tests controlen `duration_ms`.
    """

    def __init__(
        self,
        *,
        context_window: int | None = None,
        usage_totals: UsageTotals | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._context_window = context_window
        self._usage_totals = usage_totals
        self._clock = clock
        self._subagent_names: dict[str, str] = {}
        self._pending: dict[str, _PendingTool] = {}
        self._task_calls: dict[str, str] = {}
        self._tokens = [0, 0]
        self._last_input: int | None = None
        # Una revisión del plan pausa el run: el primer `interrupt` es el único que cuenta.
        self.interrupted = False

    def map(self, part: Mapping[str, Any]) -> list[SofeeEvent]:
        kind = part.get("type")
        ns = tuple(part.get("ns") or ())
        data = part.get("data")
        if kind == "messages":
            return self._on_message_chunk(ns, data)
        if kind == "updates":
            return self._on_updates(ns, data)
        if kind == "custom":
            return self._on_custom(data)
        return []

    # --- stream de tokens -------------------------------------------------------------

    def _on_message_chunk(self, ns: tuple[str, ...], data: Any) -> list[SofeeEvent]:  # noqa: ANN401
        if not isinstance(data, tuple) or len(data) != 2:
            return []
        chunk, metadata = data
        if ns and metadata.get("lc_agent_name"):
            self._subagent_names.setdefault(ns[0], str(metadata["lc_agent_name"]))
        # Solo el texto del agente principal se muestra; el de los subagentes llega como resultado.
        if ns or metadata.get("langgraph_node") != "model" or not isinstance(chunk, AIMessageChunk):
            return []
        text = text_of(chunk.content)
        return [SofeeEvent("message.delta", {"text": text})] if text else []

    # --- actualizaciones de nodo ------------------------------------------------------

    def _on_updates(self, ns: tuple[str, ...], data: Any) -> list[SofeeEvent]:  # noqa: ANN401
        if not isinstance(data, Mapping):
            return []
        events: list[SofeeEvent] = []
        for node, update in data.items():
            if node == "__interrupt__":
                events.extend(self._on_interrupt(update))
                continue
            if not isinstance(update, Mapping):
                continue
            messages = update.get("messages")
            if isinstance(messages, (list, tuple)):
                for message in messages:
                    if isinstance(message, AIMessage):
                        events.extend(self._on_ai_message(ns, message))
                    elif isinstance(message, ToolMessage):
                        events.extend(self._on_tool_result(ns, message))
            # El plan llega después del resultado de `write_todos` que lo escribió.
            if not ns and update.get("todos") is not None:
                events.append(SofeeEvent("todos.updated", {"items": todo_items(update["todos"])}))
        return events

    def _on_ai_message(self, ns: tuple[str, ...], message: AIMessage) -> list[SofeeEvent]:
        events: list[SofeeEvent] = []
        if ns and message.name:
            self._subagent_names.setdefault(ns[0], str(message.name))
        agent = self._agent_label(ns)

        usage = message.usage_metadata
        if usage:
            input_tokens = int(usage.get("input_tokens") or 0)
            self._tokens[0] += input_tokens
            self._tokens[1] += int(usage.get("output_tokens") or 0)
            if not ns:
                self._last_input = input_tokens
            events.append(self._usage_event())

        for call in message.tool_calls:
            call_id = str(call.get("id") or "")
            name = str(call.get("name") or "")
            args = dict(call.get("args") or {})
            self._pending[call_id] = _PendingTool(name, agent, args, self._clock())
            events.append(
                SofeeEvent(
                    "tool.started",
                    {"id": call_id, "name": name, "agent": agent, "args_preview": _preview(args)},
                )
            )
            if name == "task":
                subagent = str(args.get("subagent_type") or "")
                self._task_calls[call_id] = subagent
                events.append(
                    SofeeEvent(
                        "subagent.started",
                        {
                            "id": call_id,
                            "name": subagent,
                            "task": _clip(str(args.get("description") or ""), _TASK_CHARS),
                        },
                    )
                )
        return events

    def _on_tool_result(self, ns: tuple[str, ...], message: ToolMessage) -> list[SofeeEvent]:
        call_id = str(message.tool_call_id)
        pending = self._pending.pop(call_id, None)
        name = str(message.name or (pending.name if pending else ""))
        agent = pending.agent if pending else self._agent_label(ns)
        content = text_of(message.content)
        # deepagents devuelve un archivo inexistente como texto "Error: ..." con status success.
        failed = message.status == "error" or content.startswith("Error")
        status = "error" if failed else "success"
        duration_ms = int((self._clock() - pending.started_at) * 1000) if pending else 0

        events = [
            SofeeEvent(
                "tool.finished",
                {
                    "id": call_id,
                    "name": name,
                    "agent": agent,
                    "status": status,
                    "result_preview": _clip(content, _PREVIEW_CHARS),
                    "duration_ms": duration_ms,
                },
            )
        ]
        if call_id in self._task_calls:
            subagent = self._task_calls.pop(call_id)
            events.append(
                SofeeEvent(
                    "subagent.finished",
                    {
                        "id": call_id,
                        "name": subagent,
                        "status": status,
                        "summary": _clip(content, _SUMMARY_CHARS),
                    },
                )
            )
        if name in WRITE_TOOLS and not failed and pending is not None:
            path = str(pending.args.get("file_path") or "")
            if path.startswith(NOTES_PREFIX):
                # `edit_file` no trae el tamaño final: el executor lo completa desde el store.
                size = _size_of(pending.args) if name == "write_file" else None
                events.append(SofeeEvent("file.written", {"path": path, "size": size}))
        return events

    def _on_interrupt(self, value: Any) -> list[SofeeEvent]:  # noqa: ANN401
        events: list[SofeeEvent] = []
        for item in value or ():
            if self.interrupted:
                break
            payload = getattr(item, "value", None)
            todos: list[dict[str, str]] = []
            if isinstance(payload, Mapping):
                for action in payload.get("action_requests") or []:
                    if isinstance(action, Mapping) and action.get("name") == "write_todos":
                        args = action.get("args") or {}
                        todos = todo_items(args.get("todos") if isinstance(args, Mapping) else None)
            self.interrupted = True
            events.append(
                SofeeEvent(
                    "interrupt",
                    {"interrupt_id": str(item.id), "kind": "plan_review", "todos": todos},
                )
            )
        return events

    # --- stream custom ----------------------------------------------------------------

    def _on_custom(self, data: Any) -> list[SofeeEvent]:  # noqa: ANN401
        if not isinstance(data, Mapping):
            return []
        kind = data.get("type")
        if kind not in CUSTOM_EVENTS:
            return []
        return [SofeeEvent(str(kind), {k: v for k, v in data.items() if k != "type"})]

    # --- auxiliares -------------------------------------------------------------------

    def _agent_label(self, ns: tuple[str, ...]) -> str:
        if not ns:
            return MAIN_AGENT
        return self._subagent_names.get(ns[0], SUBAGENT_FALLBACK)

    def _usage_event(self) -> SofeeEvent:
        if self._usage_totals is not None:
            input_tokens, output_tokens = self._usage_totals()
        else:
            input_tokens, output_tokens = self._tokens
        percent: float | None = None
        if self._context_window and self._last_input is not None:
            percent = round(min(100.0, self._last_input * 100 / self._context_window), 1)
        return SofeeEvent(
            "usage",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "context_percent": percent,
            },
        )


def text_of(content: Any) -> str:  # noqa: ANN401
    """Texto de un contenido de mensaje: cadena, o lista de bloques de texto."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def todo_items(todos: Any) -> list[dict[str, str]]:  # noqa: ANN401
    """Normaliza la lista de `write_todos` a `{content, status}` con estados del contrato."""
    items: list[dict[str, str]] = []
    if not isinstance(todos, (list, tuple)):
        return items
    for todo in todos:
        if not isinstance(todo, Mapping):
            continue
        status = str(todo.get("status") or "pending")
        items.append(
            {
                "content": str(todo.get("content") or ""),
                "status": status if status in _TODO_STATUSES else "pending",
            }
        )
    return items


def _preview(value: Any) -> str:  # noqa: ANN401
    return _clip(json.dumps(value, ensure_ascii=False, default=str), _PREVIEW_CHARS)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _size_of(args: Mapping[str, Any]) -> int:
    return len(str(args.get("content") or "").encode("utf-8"))


__all__ = [
    "CUSTOM_EVENTS",
    "EVENT_TYPES",
    "MAIN_AGENT",
    "NOTES_PREFIX",
    "RunEventMapper",
    "SofeeEvent",
    "TERMINAL_EVENTS",
    "UsageTotals",
    "text_of",
    "todo_items",
]
