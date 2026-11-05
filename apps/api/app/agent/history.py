"""Historial que recibe el modelo en cada run, leído de la tabla `messages`.

`messages` sigue siendo la fuente de verdad de la conversación (roadmap §3.2). Reglas:
- solo mensajes `user` y `assistant` en estado `complete` o `stopped`, con texto;
- antes del mensaje de usuario que se responde (en `regenerate` y `continue`, el anterior);
- `threads.context_start_seq` (Limpiar): nada anterior a ese corte;
- `threads.summary` con `summary_through_seq` (Compactar): el resumen sustituye a los
  mensajes con seq <= ese corte, siempre que el corte caiga dentro del contexto activo.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.thread import Message, Thread
from .sources import strip_citation_markers

_ROLES = ("user", "assistant")
_STATUSES = ("complete", "stopped")

SUMMARY_HEADER = "Resumen de la conversación anterior (generado para ahorrar contexto):"
CONTINUE_INSTRUCTION = (
    "Continúa tu respuesta anterior exactamente donde se cortó. No repitas lo que ya escribiste."
)
SUMMARY_SYSTEM_PROMPT = (
    "Resumes conversaciones para poder continuarlas más tarde. Conserva los datos concretos, "
    "las decisiones, los nombres, las fuentes con su número [n] y las preguntas abiertas. "
    "Responde solo con el resumen, en el idioma de la conversación y en 400 palabras como máximo."
)


@dataclass(frozen=True)
class ContextTurn:
    seq: int
    role: str
    text: str


@dataclass(frozen=True)
class CompactionInput:
    """Lo que hay que resumir: el resumen anterior (si sigue vigente) y los turnos nuevos."""

    previous_summary: str | None
    turns: Sequence[ContextTurn]
    through_seq: int | None


def _summary_in_context(thread: Thread) -> bool:
    """El resumen vale si su corte cae dentro del contexto activo (no antes de Limpiar)."""
    floor = thread.context_start_seq or 0
    return (
        bool(thread.summary)
        and thread.summary_through_seq is not None
        and thread.summary_through_seq >= floor
    )


async def _context_turns(
    db: AsyncSession,
    thread: Thread,
    *,
    before_seq: int | None = None,
    after_seq: int | None = None,
) -> list[ContextTurn]:
    floor = thread.context_start_seq or 0
    query = select(Message.seq, Message.role, Message.text).where(
        Message.thread_id == thread.id,
        Message.seq >= floor,
        Message.role.in_(_ROLES),
        Message.status.in_(_STATUSES),
    )
    if before_seq is not None:
        query = query.where(Message.seq < before_seq)
    if after_seq is not None:
        query = query.where(Message.seq > after_seq)
    rows = (await db.execute(query.order_by(Message.seq.asc()))).all()
    return [
        ContextTurn(seq=seq, role=role, text=text)
        for seq, role, text in rows
        if text and text.strip()
    ]


async def load_model_input(
    db: AsyncSession,
    thread: Thread,
    user_message: Message,
    *,
    continue_text: str | None = None,
) -> list[BaseMessage]:
    """Mensajes de entrada del run para responder a `user_message`.

    `continue_text` (continuar una respuesta parada) se añade como turno del asistente, seguido
    de una instrucción para seguir desde ese punto.
    """
    summary_seq = thread.summary_through_seq if _summary_in_context(thread) else None
    turns = await _context_turns(
        db, thread, before_seq=user_message.seq, after_seq=summary_seq
    )

    messages: list[BaseMessage] = []
    if summary_seq is not None:
        messages.append(HumanMessage(content=f"{SUMMARY_HEADER}\n{thread.summary}"))
    for turn in turns:
        if turn.role == "user":
            messages.append(HumanMessage(content=turn.text))
        else:
            # Los `[n]` de turnos anteriores no existen en este run (la numeración reinicia).
            messages.append(AIMessage(content=strip_citation_markers(turn.text)))
    messages.append(HumanMessage(content=user_message.text))
    if continue_text:
        messages.append(AIMessage(content=continue_text))
        messages.append(HumanMessage(content=CONTINUE_INSTRUCTION))
    return messages


async def load_compaction_input(db: AsyncSession, thread: Thread) -> CompactionInput:
    """Turnos vigentes que aún no están en el resumen, y el resumen anterior si sigue valiendo."""
    after_seq = thread.summary_through_seq if _summary_in_context(thread) else None
    turns = await _context_turns(db, thread, after_seq=after_seq)
    previous = thread.summary if after_seq is not None else None
    through = turns[-1].seq if turns else None
    return CompactionInput(previous_summary=previous, turns=turns, through_seq=through)


def summary_request(compaction: CompactionInput) -> list[BaseMessage]:
    """Petición al modelo para generar el nuevo resumen (sin herramientas)."""
    lines = []
    for turn in compaction.turns:
        speaker = "Usuario" if turn.role == "user" else "Asistente"
        lines.append(f"{speaker}: {turn.text}")
    parts = []
    if compaction.previous_summary:
        parts.append(f"Resumen previo:\n{compaction.previous_summary}")
    parts.append("Conversación nueva para incorporar al resumen:\n" + "\n\n".join(lines))
    return [
        SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content="\n\n".join(parts)),
    ]


__all__ = [
    "CONTINUE_INSTRUCTION",
    "CompactionInput",
    "ContextTurn",
    "SUMMARY_HEADER",
    "load_compaction_input",
    "load_model_input",
    "summary_request",
]
