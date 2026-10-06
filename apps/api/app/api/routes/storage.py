from datetime import UTC, datetime
from urllib.parse import quote
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...db import get_session
from ...models.storage import StorageObject
from ...schemas import StorageObjectOut
from ...services.audit import write_audit
from ...services.storage import StorageBackend, generate_storage_key, get_storage_backend
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth

router = APIRouter(prefix="/storage", tags=["storage"])


async def load_object(db: AsyncSession, object_id: uuid.UUID, owner_id: uuid.UUID) -> StorageObject:
    obj = (
        await db.execute(
            select(StorageObject).where(
                StorageObject.id == object_id,
                StorageObject.owner_id == owner_id,
                StorageObject.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    return obj


@router.post("", response_model=StorageObjectOut, status_code=status.HTTP_201_CREATED)
async def upload_object(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
    backend: StorageBackend = Depends(get_storage_backend),
    file: UploadFile = File(...),
) -> StorageObjectOut:
    data = await file.read()
    if len(data) > settings.storage_max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    filename = file.filename or "file"
    content_type = file.content_type or "application/octet-stream"
    key = generate_storage_key(filename)
    await backend.put(key, data, content_type)

    obj = StorageObject(
        owner_id=auth.user.id,
        storage_key=key,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
    )
    db.add(obj)
    await db.flush()
    await write_audit(
        db,
        action="storage.object_uploaded",
        actor_id=auth.user.id,
        resource_type="storage_object",
        resource_id=str(obj.id),
        data={"filename": filename, "size_bytes": len(data), "content_type": content_type},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(obj)
    return StorageObjectOut.model_validate(obj)


@router.get("/{object_id}")
async def download_object(
    object_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
    backend: StorageBackend = Depends(get_storage_backend),
) -> Response:
    obj = await load_object(db, object_id, auth.user.id)
    try:
        data = await backend.get(obj.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Object not found")
    disposition = f"inline; filename*=UTF-8''{quote(obj.filename)}"
    return Response(
        content=data,
        media_type=obj.content_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object(
    object_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
    backend: StorageBackend = Depends(get_storage_backend),
) -> None:
    obj = await load_object(db, object_id, auth.user.id)
    await backend.delete(obj.storage_key)
    obj.deleted_at = datetime.now(UTC)
    await write_audit(
        db,
        action="storage.object_deleted",
        actor_id=auth.user.id,
        resource_type="storage_object",
        resource_id=str(obj.id),
        data={"filename": obj.filename},
        ip_address=client_ip(request),
    )
    await db.commit()