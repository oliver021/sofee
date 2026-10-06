import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.catalog import ModelCatalogBinding, ModelCatalogEntry
from ...models.provider import ProviderModel
from ...schemas.catalog import (
    CatalogBindingCreate,
    CatalogBindingOut,
    CatalogBindingUpdate,
    CatalogEntryCreate,
    CatalogEntryOut,
    CatalogEntryUpdate,
)
from ...services.audit import write_audit
from ...services.catalog import bindings_with_availability
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(
    prefix="/admin/catalog", tags=["catalog-admin"], dependencies=[Depends(require_admin)]
)


async def _load_entry(db: AsyncSession, entry_id: uuid.UUID) -> ModelCatalogEntry:
    entry = await db.get(ModelCatalogEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


async def _serialize(db: AsyncSession, entry: ModelCatalogEntry) -> CatalogEntryOut:
    rows = await bindings_with_availability(db, entry.id)
    bindings = [
        CatalogBindingOut(
            id=binding.id,
            provider_model_id=model.id,
            provider_id=provider.id,
            provider_name=provider.name,
            model_id=model.model_id,
            model_display_name=model.display_name,
            priority=binding.priority,
            is_enabled=binding.is_enabled,
            is_available=available,
        )
        for binding, model, provider, available in rows
    ]
    return CatalogEntryOut(
        id=entry.id,
        slug=entry.slug,
        display_name=entry.display_name,
        description=entry.description,
        category=entry.category,
        is_enabled=entry.is_enabled,
        sort_order=entry.sort_order,
        is_available=any(b.is_available for b in bindings),
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        bindings=bindings,
    )


@router.get("", response_model=list[CatalogEntryOut])
async def list_entries(db: AsyncSession = Depends(get_session)) -> list[CatalogEntryOut]:
    rows = (
        await db.execute(select(ModelCatalogEntry).order_by(ModelCatalogEntry.sort_order, ModelCatalogEntry.display_name))
    ).scalars()
    return [await _serialize(db, entry) for entry in rows]


@router.post("", response_model=CatalogEntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: CatalogEntryCreate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CatalogEntryOut:
    entry = ModelCatalogEntry(
        slug=payload.slug,
        display_name=payload.display_name,
        description=payload.description,
        category=payload.category,
        is_enabled=payload.is_enabled,
        sort_order=payload.sort_order,
        created_by=auth.user.id,
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists")

    await write_audit(
        db,
        action="catalog.entry_created",
        actor_id=auth.user.id,
        resource_type="catalog_entry",
        resource_id=str(entry.id),
        data={"slug": entry.slug, "display_name": entry.display_name},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(entry)
    return await _serialize(db, entry)


@router.get("/{entry_id}", response_model=CatalogEntryOut)
async def get_entry(
    entry_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> CatalogEntryOut:
    entry = await _load_entry(db, entry_id)
    return await _serialize(db, entry)


@router.patch("/{entry_id}", response_model=CatalogEntryOut)
async def update_entry(
    entry_id: uuid.UUID,
    payload: CatalogEntryUpdate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CatalogEntryOut:
    entry = await _load_entry(db, entry_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(entry, field, value)

    if changes:
        await write_audit(
            db,
            action="catalog.entry_updated",
            actor_id=auth.user.id,
            resource_type="catalog_entry",
            resource_id=str(entry.id),
            data={"changes": changes},
            ip_address=client_ip(request),
        )
    await db.commit()
    await db.refresh(entry)
    return await _serialize(db, entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    entry = await _load_entry(db, entry_id)
    await write_audit(
        db,
        action="catalog.entry_deleted",
        actor_id=auth.user.id,
        resource_type="catalog_entry",
        resource_id=str(entry.id),
        data={"slug": entry.slug},
        ip_address=client_ip(request),
    )
    await db.delete(entry)
    await db.commit()


@router.post(
    "/{entry_id}/bindings", response_model=CatalogEntryOut, status_code=status.HTTP_201_CREATED
)
async def add_binding(
    entry_id: uuid.UUID,
    payload: CatalogBindingCreate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CatalogEntryOut:
    entry = await _load_entry(db, entry_id)
    model = await db.get(ProviderModel, payload.provider_model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    priority = payload.priority
    if priority is None:
        current_max = (
            await db.execute(
                select(ModelCatalogBinding.priority)
                .where(ModelCatalogBinding.catalog_entry_id == entry_id)
                .order_by(ModelCatalogBinding.priority.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        priority = 0 if current_max is None else current_max + 1

    binding = ModelCatalogBinding(
        catalog_entry_id=entry_id, provider_model_id=model.id, priority=priority
    )
    db.add(binding)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Model already bound to this entry"
        )

    await write_audit(
        db,
        action="catalog.binding_added",
        actor_id=auth.user.id,
        resource_type="catalog_entry",
        resource_id=str(entry.id),
        data={"provider_model_id": str(model.id), "model_id": model.model_id},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(entry)
    return await _serialize(db, entry)


@router.patch("/{entry_id}/bindings/{binding_id}", response_model=CatalogEntryOut)
async def update_binding(
    entry_id: uuid.UUID,
    binding_id: uuid.UUID,
    payload: CatalogBindingUpdate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CatalogEntryOut:
    entry = await _load_entry(db, entry_id)
    binding = await db.get(ModelCatalogBinding, binding_id)
    if binding is None or binding.catalog_entry_id != entry_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(binding, field, value)

    if changes:
        await write_audit(
            db,
            action="catalog.binding_updated",
            actor_id=auth.user.id,
            resource_type="catalog_entry",
            resource_id=str(entry.id),
            data={"binding_id": str(binding.id), "changes": changes},
            ip_address=client_ip(request),
        )
    await db.commit()
    await db.refresh(entry)
    return await _serialize(db, entry)


@router.delete("/{entry_id}/bindings/{binding_id}", response_model=CatalogEntryOut)
async def remove_binding(
    entry_id: uuid.UUID,
    binding_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CatalogEntryOut:
    entry = await _load_entry(db, entry_id)
    binding = await db.get(ModelCatalogBinding, binding_id)
    if binding is None or binding.catalog_entry_id != entry_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")

    await write_audit(
        db,
        action="catalog.binding_removed",
        actor_id=auth.user.id,
        resource_type="catalog_entry",
        resource_id=str(entry.id),
        data={"binding_id": str(binding.id)},
        ip_address=client_ip(request),
    )
    await db.delete(binding)
    await db.commit()
    await db.refresh(entry)
    return await _serialize(db, entry)
