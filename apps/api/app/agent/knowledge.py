"""Archivos que el agente ve: `/kb/` (documentos del equipo) y `/attachments/` (adjuntos del hilo).

La copia en el store es lo que lee el agente; `kb_documents` y `storage_objects` siguen siendo
la fuente de verdad (roadmap §3.5). Dos piezas:
- `mirror_document` / `unmirror_document`: el admin las llama al crear, editar, activar,
  desactivar o borrar un documento. El valor tiene la forma exacta de `StoreBackend`.
- `prepare_run_knowledge`: al empezar cada run copia los adjuntos del mensaje y deja en el
  registro del run la ruta virtual de cada documento, para que las citas apunten a su id.
"""

import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from langgraph.store.base import BaseStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import async_session_factory
from ..models.agent import AgentRun
from ..models.kb import KbDocument
from ..models.storage import StorageObject
from ..models.thread import Message
from ..services.knowledge import enabled_documents, kb_path
from .backends import KB_NAMESPACE
from .context import SofeeContext
from .sources import DocumentRef, get_registry

ATTACHMENTS_NAMESPACE_SUFFIX = "attachments"
ATTACHMENTS_PREFIX = "/attachments/"
_ATTACHMENT_STEM_MAX = 80


def store_key(slug: str) -> str:
    """Clave dentro del namespace `("kb",)`. La ruta `/kb/` se quita antes de llegar al store."""
    return f"/{slug}.md"


def _file_value(content: str, created_at: datetime) -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    return {
        "content": content,
        "encoding": "utf-8",
        "created_at": created_at.astimezone(UTC).isoformat(),
        "modified_at": now,
    }


async def mirror_document(store: BaseStore, document: KbDocument) -> None:
    """Escribe o actualiza `/kb/<slug>.md` con el texto extraído del documento."""
    await store.aput(
        KB_NAMESPACE,
        store_key(document.slug),
        _file_value(document.text, document.created_at),
    )


async def unmirror_document(store: BaseStore, slug: str) -> None:
    """Quita `/kb/<slug>.md`: el agente deja de verlo al momento."""
    await store.adelete(KB_NAMESPACE, store_key(slug))


async def prepare_run_knowledge(run: SofeeContext, store: BaseStore) -> None:
    """Prepara `/attachments/` y el mapa de documentos del run antes de invocar al agente."""
    registry = get_registry(run.run_id)
    async with async_session_factory() as db:
        for document in await enabled_documents(db):
            registry.documents[kb_path(document.slug)] = DocumentRef(
                ref=document.document_id, title=document.title
            )
        attachments = await _message_attachments(db, run)

    thread_namespace = (run.thread_id, ATTACHMENTS_NAMESPACE_SUFFIX)
    taken: set[str] = set()
    now = datetime.now(UTC)
    for obj in attachments:
        if obj.extracted_text is None:
            continue
        name = _attachment_name(obj.filename, taken)
        await store.aput(
            thread_namespace,
            f"/{name}",
            _file_value(obj.extracted_text, now),
        )
        registry.documents[f"{ATTACHMENTS_PREFIX}{name}"] = DocumentRef(
            ref=str(obj.id), title=obj.filename
        )


async def _message_attachments(db: AsyncSession, run: SofeeContext) -> list[StorageObject]:
    """Adjuntos del mensaje que este run responde, solo los del propio usuario y no borrados."""
    agent_run = await db.get(AgentRun, uuid.UUID(run.run_id))
    if agent_run is None or agent_run.user_message_id is None:
        return []
    message = await db.get(Message, agent_run.user_message_id)
    ids = _uuid_list(message.attachment_ids if message is not None else None)
    if not ids:
        return []
    rows = (
        await db.execute(
            select(StorageObject)
            .where(
                StorageObject.id.in_(ids),
                StorageObject.owner_id == agent_run.user_id,
                StorageObject.deleted_at.is_(None),
            )
            .order_by(StorageObject.created_at, StorageObject.id)
        )
    ).scalars()
    return list(rows)


def _uuid_list(values: list[str] | None) -> list[uuid.UUID]:
    """Ids válidos de la lista; un id mal formado se ignora en lugar de romper el run."""
    result: list[uuid.UUID] = []
    for value in values or []:
        try:
            result.append(uuid.UUID(str(value)))
        except ValueError:
            continue
    return result


def _attachment_name(filename: str, taken: set[str]) -> str:
    """Nombre de archivo seguro dentro de `/attachments/`, sin colisiones dentro del run."""
    base = PurePosixPath(filename).name or "adjunto"
    stem, ext = os.path.splitext(base)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")[:_ATTACHMENT_STEM_MAX] or "adjunto"
    safe_ext = re.sub(r"[^A-Za-z0-9.]", "", ext)[:10]
    name = f"{safe_stem}{safe_ext}"
    number = 2
    while name in taken:
        name = f"{safe_stem}-{number}{safe_ext}"
        number += 1
    taken.add(name)
    return name


__all__ = [
    "ATTACHMENTS_PREFIX",
    "mirror_document",
    "prepare_run_knowledge",
    "store_key",
    "unmirror_document",
]
