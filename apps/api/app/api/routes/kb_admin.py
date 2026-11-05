"""Base de conocimiento del equipo en el admin: subir, revisar, editar, retirar.

Cada alta, edición, activación, desactivación o borrado actualiza también la copia que ve el
agente en `/kb/` (ver `app/agent/knowledge.py`). Todo queda auditado.
"""

import asyncio
import uuid
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.knowledge import mirror_document, unmirror_document
from ...agent.persistence import get_agent_storage
from ...config import settings
from ...db import get_session
from ...models.kb import KbDocument
from ...schemas.knowledge import KbDocumentOut, KbDocumentUpdate, KbRejectedFile, KbTextOut, KbUploadOut
from ...services.audit import write_audit
from ...services.extraction import (
    CONTENT_TYPES,
    SUPPORTED_EXTENSIONS,
    ExtractionError,
    extension_of,
    extract_text,
)
from ...services.knowledge import MAX_TAGS, kb_path, normalize_tags, slugify, title_for, unique_slug
from ...services.rag import index_document_safely
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(prefix="/admin/kb", tags=["kb-admin"], dependencies=[Depends(require_admin)])

# Texto que devuelve la vista previa. Un documento entero puede ser muy grande para el panel.
PREVIEW_CHARS = 50_000


async def _load(db: AsyncSession, document_id: uuid.UUID) -> KbDocument:
    document = await db.get(KbDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _serialize(document: KbDocument, text_chars: int) -> KbDocumentOut:
    return KbDocumentOut(
        id=document.id,
        slug=document.slug,
        title=document.title,
        path=document.path,
        source_filename=document.source_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        tags=list(document.tags or []),
        is_enabled=document.is_enabled,
        text_chars=text_chars,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=list[KbDocumentOut])
async def list_documents(
    q: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_session),
) -> list[KbDocumentOut]:
    query = select(KbDocument, func.length(KbDocument.text)).order_by(KbDocument.title)
    if q and q.strip():
        query = query.where(KbDocument.title.icontains(q.strip(), autoescape=True))
    rows = (await db.execute(query)).all()
    return [_serialize(document, int(length or 0)) for document, length in rows]


@router.post("", response_model=KbUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_documents(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
    files: list[UploadFile] = File(...),
) -> KbUploadOut:
    """Sube uno o varios archivos (md, txt, pdf). Cada uno se valora por separado: los que
    fallan vuelven en `rejected` y no impiden crear los demás."""
    created: list[KbDocument] = []
    rejected: list[KbRejectedFile] = []
    reserved_slugs: set[str] = set()

    for upload in files:
        filename = PurePosixPath(upload.filename or "documento").name or "documento"
        suffix = extension_of(filename)
        if suffix not in SUPPORTED_EXTENSIONS:
            rejected.append(KbRejectedFile(filename=filename, reason="unsupported_type"))
            continue
        data = await upload.read()
        if len(data) > settings.storage_max_upload_bytes:
            rejected.append(KbRejectedFile(filename=filename, reason="too_large"))
            continue
        try:
            text = await asyncio.to_thread(extract_text, filename, data)
        except ExtractionError:
            rejected.append(KbRejectedFile(filename=filename, reason="extraction_failed"))
            continue

        slug = await unique_slug(db, slugify(PurePosixPath(filename).stem), reserved_slugs)
        document = KbDocument(
            slug=slug,
            title=title_for(filename, text),
            path=kb_path(slug),
            source_filename=filename,
            content_type=CONTENT_TYPES[suffix],
            text=text,
            tags=[],
            is_enabled=True,
            size_bytes=len(data),
            created_by=auth.user.id,
        )
        db.add(document)
        await db.flush()
        await write_audit(
            db,
            action="kb.document_uploaded",
            actor_id=auth.user.id,
            resource_type="kb_document",
            resource_id=str(document.id),
            data={"slug": slug, "filename": filename, "size_bytes": len(data), "text_chars": len(text)},
            ip_address=client_ip(request),
        )
        created.append(document)

    await db.commit()
    store = get_agent_storage().store
    for document in created:
        await db.refresh(document)
        await mirror_document(store, document)
        await index_document_safely(db, document)
    await db.commit()
    return KbUploadOut(
        documents=[_serialize(document, len(document.text)) for document in created],
        rejected=rejected,
    )


@router.get("/{document_id}/text", response_model=KbTextOut)
async def document_text(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> KbTextOut:
    """Texto extraído: lo que el agente lee de verdad. Se recorta a `PREVIEW_CHARS`."""
    document = await _load(db, document_id)
    return KbTextOut(
        id=document.id,
        title=document.title,
        text=document.text[:PREVIEW_CHARS],
        text_chars=len(document.text),
        truncated=len(document.text) > PREVIEW_CHARS,
    )


@router.patch("/{document_id}", response_model=KbDocumentOut)
async def update_document(
    document_id: uuid.UUID,
    payload: KbDocumentUpdate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> KbDocumentOut:
    """Cambia título, etiquetas o si está activo. Un `null` explícito no cambia nada."""
    document = await _load(db, document_id)
    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if "title" in changes:
        changes["title"] = changes["title"].strip()
        if not changes["title"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Title is blank")
    if "tags" in changes:
        changes["tags"] = normalize_tags(changes["tags"])[:MAX_TAGS]
    for field, value in changes.items():
        setattr(document, field, value)
    await write_audit(
        db,
        action="kb.document_updated",
        actor_id=auth.user.id,
        resource_type="kb_document",
        resource_id=str(document.id),
        data={"slug": document.slug, **changes},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(document)

    store = get_agent_storage().store
    if document.is_enabled:
        await mirror_document(store, document)
    else:
        await unmirror_document(store, document.slug)
    return _serialize(document, len(document.text))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    document = await _load(db, document_id)
    slug = document.slug
    await write_audit(
        db,
        action="kb.document_deleted",
        actor_id=auth.user.id,
        resource_type="kb_document",
        resource_id=str(document.id),
        data={"slug": slug, "title": document.title},
        ip_address=client_ip(request),
    )
    await db.delete(document)
    await db.commit()
    await unmirror_document(get_agent_storage().store, slug)

