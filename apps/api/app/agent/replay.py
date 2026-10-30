"""Modo replay: el plan B de la demo (roadmap §2 y F6).

`app_settings['replay.map']` es una lista de `{prompt, run_id}`. Si el mensaje de un run `send`
coincide con un `prompt` (tras normalizarlo) y ese `run_id` es un run completado, el executor
reemite sus eventos con el ritmo original en lugar de llamar al modelo. El run nuevo se persiste
como cualquier otro, pero no usa modelo, así que no gasta tokens ni cuota de tokens.

Dos reglas: solo se reproducen runs `completed` (un fallo grabado no se enseña en una demo) y los
`interrupt` se omiten, porque sin checkpoint no hay nada que reanudar.
"""

import itertools
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentRun, AgentRunEvent
from ..services.app_settings import get_setting

REPLAY_KEY = "replay.map"
# Pausa máxima entre dos eventos grabados: un silencio de 30 s en la grabación no se repite en directo.
REPLAY_MAX_GAP_SECONDS = 2.0
# Signos que los teclados añaden o quitan al escribir una pregunta; no cambian lo que se pregunta.
_EDGE_PUNCTUATION = " ¿?¡!.,;:"


@dataclass(frozen=True)
class RecordedEvent:
    type: str
    payload: dict[str, Any]
    created_at: datetime | None


@dataclass(frozen=True)
class Recording:
    run_id: uuid.UUID
    model_label: str | None
    events: tuple[RecordedEvent, ...]


def normalise_prompt(text: str) -> str:
    """Minúsculas, sin tildes, con espacios colapsados y sin signos de los bordes."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.casefold().split()).strip(_EDGE_PUNCTUATION)


async def find_recording(db: AsyncSession, prompt: str) -> Recording | None:
    """Primer run grabado del mapa que responde a `prompt`, o None (el agente responde en vivo)."""
    wanted = normalise_prompt(prompt)
    if not wanted:
        return None
    entries = await get_setting(db, REPLAY_KEY, [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict) or normalise_prompt(str(entry.get("prompt") or "")) != wanted:
            continue
        run_id = _as_uuid(entry.get("run_id"))
        recording = await _completed_recording(db, run_id) if run_id is not None else None
        if recording is not None:
            return recording
    return None


def pacing(events: Sequence[RecordedEvent]) -> list[float]:
    """Pausa antes de cada evento: la distancia con el anterior, acotada a `REPLAY_MAX_GAP_SECONDS`.

    Sin marca de tiempo, o con una que retrocede, la pausa es cero.
    """
    if not events:
        return []
    gaps = [0.0]
    for previous, current in itertools.pairwise(events):
        if previous.created_at is None or current.created_at is None:
            gaps.append(0.0)
            continue
        elapsed = (current.created_at - previous.created_at).total_seconds()
        gaps.append(min(max(elapsed, 0.0), REPLAY_MAX_GAP_SECONDS))
    return gaps


def rebase_payload(payload: dict[str, Any], *, run_id: str, assistant_id: str, mode: str) -> dict[str, Any]:
    """El payload con los ids y el modo de este run: el grabado trae los suyos."""
    rebased = dict(payload)
    if "run_id" in rebased:
        rebased["run_id"] = run_id
    if "assistant_message_id" in rebased:
        rebased["assistant_message_id"] = assistant_id
    if "mode" in rebased:
        rebased["mode"] = mode
    return rebased


async def _completed_recording(db: AsyncSession, run_id: uuid.UUID) -> Recording | None:
    run = await db.get(AgentRun, run_id)
    if run is None or run.status != "completed":
        return None
    rows = (
        await db.execute(
            select(AgentRunEvent.type, AgentRunEvent.payload, AgentRunEvent.created_at)
            .where(AgentRunEvent.run_id == run_id)
            .order_by(AgentRunEvent.seq.asc())
        )
    ).all()
    if not rows or rows[-1].type != "run.completed":
        return None
    events = tuple(
        RecordedEvent(type=row.type, payload=dict(row.payload or {}), created_at=row.created_at)
        for row in rows
    )
    return Recording(run_id=run.id, model_label=run.model_label, events=events)


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


__all__ = [
    "REPLAY_KEY",
    "REPLAY_MAX_GAP_SECONDS",
    "RecordedEvent",
    "Recording",
    "find_recording",
    "normalise_prompt",
    "pacing",
    "rebase_payload",
]
