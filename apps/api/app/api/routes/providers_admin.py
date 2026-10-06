import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_session
from ...models.provider import Provider, ProviderCredential, ProviderModel
from ...schemas.provider import (
    ConnectionTestResult,
    CredentialOut,
    CredentialRotateRequest,
    CredentialRotateResponse,
    ModelOut,
    ModelSyncResult,
    ModelToggleRequest,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)
from ...services.audit import redact_headers, write_audit
from ...services.providers import (
    ProviderError,
    build_adapter_for_provider,
    create_credential,
    get_active_credential,
)
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(
    prefix="/admin/providers",
    tags=["admin:providers"],
    dependencies=[Depends(require_admin)],
)


async def load_provider(db: AsyncSession, provider_id: uuid.UUID) -> Provider:
    provider = (
        await db.execute(
            select(Provider).where(Provider.id == provider_id).options(
                selectinload(Provider.models)
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _serialize(provider: Provider, credential: ProviderCredential | None) -> ProviderOut:
    out = ProviderOut.model_validate(provider)
    out.credential_last_four = credential.last_four if credential is not None else None
    return out


@router.get("", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_session)) -> list[ProviderOut]:
    providers = (
        await db.execute(
            select(Provider).options(
                selectinload(Provider.credentials)
            ).order_by(Provider.name)
        )
    ).scalars()
    result: list[ProviderOut] = []
    for provider in providers:
        active = next((c for c in provider.credentials if c.is_active), None)
        result.append(_serialize(provider, active))
    return result


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ProviderOut:
    existing = (
        await db.execute(select(Provider).where(Provider.name == payload.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Provider name already exists")

    provider = Provider(
        name=payload.name,
        kind=payload.kind,
        base_url=payload.base_url or None,
        is_enabled=payload.is_enabled,
        default_headers=payload.default_headers or None,
        created_by=auth.user.id,
    )
    db.add(provider)
    await db.flush()

    credential = None
    if payload.initial_api_key:
        credential = await create_credential(
            db, provider.id, payload.initial_api_key, auth.user.id, deactivate_previous=False
        )

    await write_audit(
        db,
        action="provider.created",
        actor_id=auth.user.id,
        resource_type="provider",
        resource_id=str(provider.id),
        data={
            "name": provider.name,
            "kind": provider.kind.value,
            "has_initial_key": bool(payload.initial_api_key),
        },
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(provider)
    return _serialize(provider, credential)


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(
    provider_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> ProviderOut:
    provider = await load_provider(db, provider_id)
    credential = await get_active_credential(db, provider.id)
    return _serialize(provider, credential)


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderUpdate,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ProviderOut:
    provider = await load_provider(db, provider_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(provider, field, value)
    audit_data = dict(changes)
    if "base_url" in changes and changes["base_url"] == "":
        provider.base_url = None
        audit_data["base_url"] = None
    if audit_data.get("default_headers") is not None:
        audit_data["default_headers"] = redact_headers(audit_data["default_headers"])
    try:
        await write_audit(
            db,
            action="provider.updated",
            actor_id=auth.user.id,
            resource_type="provider",
            resource_id=str(provider.id),
            data=audit_data,
            ip_address=client_ip(request),
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Provider name already exists")
    await db.refresh(provider)
    credential = await get_active_credential(db, provider.id)
    return _serialize(provider, credential)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    provider = await load_provider(db, provider_id)
    await write_audit(
        db,
        action="provider.deleted",
        actor_id=auth.user.id,
        resource_type="provider",
        resource_id=str(provider.id),
        data={"name": provider.name, "kind": provider.kind.value},
        ip_address=client_ip(request),
    )
    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/test", response_model=ConnectionTestResult)
async def test_provider(
    provider_id: uuid.UUID,
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ConnectionTestResult:
    provider = await load_provider(db, provider_id)
    try:
        adapter = await build_adapter_for_provider(db, provider)
        result = await adapter.test_connection()
    except ProviderError as exc:
        return ConnectionTestResult(ok=False, message=str(exc))
    return ConnectionTestResult(
        ok=result.ok, message=result.message, model_count=result.model_count
    )


@router.post("/{provider_id}/credentials", response_model=CredentialRotateResponse)
async def rotate_credential(
    provider_id: uuid.UUID,
    payload: CredentialRotateRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> CredentialRotateResponse:
    provider = await load_provider(db, provider_id)
    previous = await get_active_credential(db, provider.id)
    previous_last_four = previous.last_four if previous is not None else None

    credential = await create_credential(
        db, provider.id, payload.api_key, auth.user.id, deactivate_previous=True
    )
    await write_audit(
        db,
        action="provider.credential_rotated",
        actor_id=auth.user.id,
        resource_type="provider",
        resource_id=str(provider.id),
        data={"last_four": credential.last_four, "previous_last_four": previous_last_four},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(credential)
    return CredentialRotateResponse(
        credential=CredentialOut.model_validate(credential),
        previous_last_four=previous_last_four,
    )


@router.get("/{provider_id}/credentials", response_model=list[CredentialOut])
async def list_credentials(
    provider_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> list[CredentialOut]:
    await load_provider(db, provider_id)
    rows = (
        await db.execute(
            select(ProviderCredential)
            .where(ProviderCredential.provider_id == provider_id)
            .order_by(ProviderCredential.created_at.desc())
        )
    ).scalars()
    return [CredentialOut.model_validate(c) for c in rows]


@router.get("/{provider_id}/models", response_model=list[ModelOut])
async def list_provider_models(
    provider_id: uuid.UUID, db: AsyncSession = Depends(get_session)
) -> list[ModelOut]:
    await load_provider(db, provider_id)
    rows = (
        await db.execute(
            select(ProviderModel)
            .where(ProviderModel.provider_id == provider_id)
            .order_by(ProviderModel.model_id)
        )
    ).scalars()
    return [ModelOut.model_validate(m) for m in rows]


@router.post("/{provider_id}/models/sync", response_model=ModelSyncResult)
async def sync_provider_models(
    provider_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ModelSyncResult:
    provider = await load_provider(db, provider_id)
    try:
        adapter = await build_adapter_for_provider(db, provider)
        remote_models = await adapter.list_models()
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    existing = {
        m.model_id: m
        for m in (
            await db.execute(
                select(ProviderModel).where(ProviderModel.provider_id == provider.id)
            )
        ).scalars()
    }
    created = 0
    already = 0
    updated: list[ProviderModel] = []
    for info in remote_models:
        model = existing.get(info.id)
        if model is None:
            model = ProviderModel(
                provider_id=provider.id,
                model_id=info.id,
                display_name=info.display_name or info.id,
                is_enabled=True,
            )
            db.add(model)
            created += 1
        else:
            already += 1
        new_display = info.display_name or info.id
        if model.display_name != new_display:
            model.display_name = new_display
        updated.append(model)

    await write_audit(
        db,
        action="provider.models_synced",
        actor_id=auth.user.id,
        resource_type="provider",
        resource_id=str(provider.id),
        data={"created": created, "already_exists": already, "total": len(updated)},
        ip_address=client_ip(request),
    )
    await db.commit()
    updated.sort(key=lambda m: m.model_id)
    return ModelSyncResult(
        created=created,
        already_exists=already,
        total=len(updated),
        models=[ModelOut.model_validate(m) for m in updated],
    )


@router.patch("/{provider_id}/models/{model_id}", response_model=ModelOut)
async def toggle_provider_model(
    provider_id: uuid.UUID,
    model_id: uuid.UUID,
    payload: ModelToggleRequest,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ModelOut:
    model = (
        await db.execute(
            select(ProviderModel).where(
                ProviderModel.id == model_id,
                ProviderModel.provider_id == provider_id,
            )
        )
    ).scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Provider model not found")
    model.is_enabled = payload.is_enabled
    await write_audit(
        db,
        action="provider.model_toggled",
        actor_id=auth.user.id,
        resource_type="provider",
        resource_id=str(provider_id),
        data={
            "model_id": model.model_id,
            "display_name": model.display_name,
            "is_enabled": model.is_enabled,
        },
        ip_address=client_ip(request),
    )
    await db.commit()
    return ModelOut.model_validate(model)