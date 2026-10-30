"""Admin del agente: perfiles por modo (con versiones y rollback) y ajustes globales.

Cada mutación exige X-CSRF-Token y queda en la auditoría. Los perfiles no se editan en la BD a mano:
una versión nueva siempre queda activa, y un run guarda la versión con la que se ejecutó.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.profiles import MODES
from ...db import get_session
from ...schemas.agent_admin import AgentProfileIn, AgentProfileOut, AgentSettings
from ...services.agent_config import (
    ConfigInvalid,
    activate_version,
    active_version_number,
    create_version,
    find_version,
    missing_run_ids,
    mode_profile,
    read_settings,
    validate_profile_config,
    write_settings,
)
from ...services.audit import write_audit
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(
    prefix="/admin/agent",
    tags=["admin:agent"],
    dependencies=[Depends(require_admin)],
)


def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent mode")


@router.get("/profiles", response_model=list[AgentProfileOut])
async def list_profiles(db: AsyncSession = Depends(get_session)) -> list[AgentProfileOut]:
    return [await mode_profile(db, mode) for mode in MODES]


@router.post("/profiles/{mode}", response_model=AgentProfileOut, status_code=status.HTTP_201_CREATED)
async def create_profile_version(
    mode: str,
    payload: AgentProfileIn,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> AgentProfileOut:
    """Crea una versión nueva del perfil y la activa. Lo que falte en `config` viene de los defaults."""
    _check_mode(mode)
    try:
        config = validate_profile_config(mode, payload.config)
    except ConfigInvalid as exc:
        raise HTTPException(status_code=422, detail=exc.errors)

    previous = await active_version_number(db, mode)
    try:
        row = await create_version(
            db,
            mode,
            system_prompt=payload.system_prompt,
            config=config,
            actor_id=auth.user.id,
        )
    except IntegrityError:
        # Dos guardados a la vez con el mismo número: el segundo se reintenta.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile version conflict, retry")

    await write_audit(
        db,
        action="agent.profile_version_created",
        actor_id=auth.user.id,
        resource_type="agent_profile",
        resource_id=mode,
        data={"mode": mode, "version": row.version, "previous_version": previous},
        ip_address=client_ip(request),
    )
    await db.commit()
    return await mode_profile(db, mode)


@router.post("/profiles/{mode}/activate/{version}", response_model=AgentProfileOut)
async def activate_profile_version(
    mode: str,
    version: int,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> AgentProfileOut:
    """Rollback: vuelve a activar una versión anterior del perfil."""
    _check_mode(mode)
    row = await find_version(db, mode, version)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile version not found")

    previous = await active_version_number(db, mode)
    try:
        await activate_version(db, row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile version conflict, retry")
    await write_audit(
        db,
        action="agent.profile_version_activated",
        actor_id=auth.user.id,
        resource_type="agent_profile",
        resource_id=mode,
        data={"mode": mode, "version": row.version, "previous_version": previous},
        ip_address=client_ip(request),
    )
    await db.commit()
    return await mode_profile(db, mode)


@router.get("/settings", response_model=AgentSettings)
async def get_settings(db: AsyncSession = Depends(get_session)) -> AgentSettings:
    return await read_settings(db)


@router.put("/settings", response_model=AgentSettings)
async def put_settings(
    payload: AgentSettings,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> AgentSettings:
    """Reemplaza los ajustes del agente. `enabled: false` es el interruptor general de mantenimiento."""
    missing = await missing_run_ids(db, [entry.run_id for entry in payload.replay_map])
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Runs no encontrados en replay_map: {', '.join(str(run_id) for run_id in missing)}",
        )
    changes = await write_settings(db, payload, auth.user.id)
    await write_audit(
        db,
        action="agent.settings_updated",
        actor_id=auth.user.id,
        resource_type="agent_settings",
        resource_id=None,
        data={"changed": changes},
        ip_address=client_ip(request),
    )
    await db.commit()
    return await read_settings(db)


__all__ = ["router"]
