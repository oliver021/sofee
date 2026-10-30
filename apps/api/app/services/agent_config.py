"""Perfiles y ajustes del agente en el admin: versiones, activación, validación y lectura/escritura.

Los defaults de código (`app/agent/profiles.py`) son la versión implícita de cada modo: sin filas en
`agent_profiles`, el modo usa esos defaults. Cada cambio crea una versión nueva y la deja activa;
revertir es activar una versión anterior. Un run guarda la versión que usó (`profile_version_id`).
"""

import uuid
from copy import deepcopy
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.profiles import DEFAULT_PROFILES
from ..models.agent import AgentProfile, AgentRun
from ..models.app_setting import AppSetting
from ..models.user import User
from ..schemas.agent_admin import (
    AgentProfileOut,
    AgentSettings,
    ProfileConfig,
    ProfileVersionOut,
)
from .app_settings import agent_enabled, get_setting

# Claves de `app_settings` que escribe el admin (ver docs/deep-agent-roadmap.md §3.11).
KEY_ENABLED = "agent.enabled"
KEY_STARTERS = "starters"
KEY_REPLAY = "replay.map"
KEY_QUOTAS = "quotas"


class ConfigInvalid(Exception):
    """La configuración de un perfil no es válida. `errors` tiene el formato de pydantic."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("invalid profile config")
        self.errors = errors


# --- perfiles -----------------------------------------------------------------------------


def merge_over_defaults(mode: str, override: dict[str, Any]) -> dict[str, Any]:
    """Defaults del modo con lo que envió el admin encima. `limits` se fusiona; el resto se reemplaza."""
    merged = deepcopy(DEFAULT_PROFILES[mode]["config"])
    for key, value in override.items():
        if key == "limits" and isinstance(value, dict):
            merged["limits"] = {**merged.get("limits", {}), **value}
        else:
            merged[key] = deepcopy(value)
    return merged


def validate_profile_config(mode: str, override: dict[str, Any]) -> dict[str, Any]:
    """Configuración completa y validada, lista para guardar como snapshot de la versión."""
    try:
        return ProfileConfig.model_validate(merge_over_defaults(mode, override)).model_dump(mode="json")
    except ValidationError as exc:
        raise ConfigInvalid(exc.errors(include_url=False, include_context=False, include_input=False)) from exc


def _version_out(row: AgentProfile, email: str | None) -> ProfileVersionOut:
    return ProfileVersionOut(
        id=row.id,
        version=row.version,
        is_active=row.is_active,
        system_prompt=row.system_prompt,
        config=row.config or {},
        created_by_email=email,
        created_at=row.created_at,
    )


async def profile_history(db: AsyncSession, mode: str) -> list[ProfileVersionOut]:
    """Todas las versiones del modo, de la más nueva a la más antigua."""
    rows = (
        await db.execute(
            select(AgentProfile, User.email)
            .outerjoin(User, User.id == AgentProfile.created_by)
            .where(AgentProfile.mode == mode)
            .order_by(AgentProfile.version.desc())
        )
    ).all()
    return [_version_out(row, email) for row, email in rows]


async def mode_profile(db: AsyncSession, mode: str) -> AgentProfileOut:
    """Versión activa del modo (o los defaults de código si no hay ninguna fila) y su historial."""
    history = await profile_history(db, mode)
    active = next((item for item in history if item.is_active), None)
    if active is None:
        defaults = DEFAULT_PROFILES[mode]
        active = ProfileVersionOut(
            id=None,
            version=None,
            is_active=True,
            system_prompt=defaults["system_prompt"],
            config=deepcopy(defaults["config"]),
        )
    return AgentProfileOut(mode=mode, active=active, history=history)


async def latest_version_number(db: AsyncSession, mode: str) -> int | None:
    return (
        await db.execute(select(func.max(AgentProfile.version)).where(AgentProfile.mode == mode))
    ).scalar_one()


async def active_version_number(db: AsyncSession, mode: str) -> int | None:
    return (
        await db.execute(
            select(AgentProfile.version).where(AgentProfile.mode == mode, AgentProfile.is_active.is_(True))
        )
    ).scalar_one_or_none()


async def create_version(
    db: AsyncSession,
    mode: str,
    *,
    system_prompt: str,
    config: dict[str, Any],
    actor_id: uuid.UUID,
) -> AgentProfile:
    """Crea la versión siguiente y la deja como única activa del modo. No commitea."""
    next_version = ((await latest_version_number(db, mode)) or 0) + 1
    await _deactivate(db, mode)
    row = AgentProfile(
        mode=mode,
        version=next_version,
        is_active=True,
        system_prompt=system_prompt,
        config=config,
        created_by=actor_id,
    )
    db.add(row)
    await db.flush()
    return row


async def find_version(db: AsyncSession, mode: str, version: int) -> AgentProfile | None:
    return (
        await db.execute(
            select(AgentProfile).where(AgentProfile.mode == mode, AgentProfile.version == version)
        )
    ).scalar_one_or_none()


async def activate_version(db: AsyncSession, row: AgentProfile) -> None:
    """Deja `row` como la única versión activa de su modo (rollback). No commitea."""
    await _deactivate(db, row.mode)
    row.is_active = True
    await db.flush()


async def _deactivate(db: AsyncSession, mode: str) -> None:
    # Antes del INSERT/UPDATE activo: el índice parcial solo admite una fila activa por modo.
    await db.execute(
        update(AgentProfile)
        .where(AgentProfile.mode == mode, AgentProfile.is_active.is_(True))
        .values(is_active=False)
    )


# --- ajustes ------------------------------------------------------------------------------


async def read_settings(db: AsyncSession) -> AgentSettings:
    replay = await get_setting(db, KEY_REPLAY, [])
    return AgentSettings.model_validate(
        {
            "enabled": await agent_enabled(db),
            "starters": await get_setting(db, KEY_STARTERS, {}),
            "replay_map": replay if isinstance(replay, list) else [],
            "quotas": await get_setting(db, KEY_QUOTAS, {}),
        }
    )


async def missing_run_ids(db: AsyncSession, run_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if not run_ids:
        return []
    found = set(
        (await db.execute(select(AgentRun.id).where(AgentRun.id.in_(run_ids)))).scalars().all()
    )
    return [run_id for run_id in run_ids if run_id not in found]


async def write_settings(db: AsyncSession, payload: AgentSettings, actor_id: uuid.UUID) -> dict[str, Any]:
    """Guarda los cuatro ajustes. Devuelve `{clave: {from, to}}` solo de lo que cambió. No commitea."""
    values: dict[str, Any] = {
        KEY_ENABLED: payload.enabled,
        KEY_STARTERS: {
            mode: {locale: list(texts) for locale, texts in by_locale.items()}
            for mode, by_locale in payload.starters.items()
        },
        KEY_REPLAY: [{"prompt": entry.prompt, "run_id": str(entry.run_id)} for entry in payload.replay_map],
        KEY_QUOTAS: {role.value: limits.model_dump(mode="json") for role, limits in payload.quotas.items()},
    }
    changes: dict[str, Any] = {}
    for key, value in values.items():
        row = await db.get(AppSetting, key)
        previous = None if row is None else row.value
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=actor_id))
        else:
            row.value = value
            row.updated_by = actor_id
        if previous != value:
            changes[key] = {"from": previous, "to": value}
    await db.flush()
    return changes


__all__ = [
    "ConfigInvalid",
    "activate_version",
    "active_version_number",
    "create_version",
    "find_version",
    "merge_over_defaults",
    "missing_run_ids",
    "mode_profile",
    "profile_history",
    "read_settings",
    "validate_profile_config",
    "write_settings",
]
