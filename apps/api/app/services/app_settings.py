"""Lectura de los ajustes globales del agente (`app_settings`).

Claves: `agent.enabled` (bool, por defecto true), `quotas` ({rol: {runs_per_day,
tokens_per_day}}) y `starters` ({modo: {idioma: [texto, ...]}}). Una clave que falta o
con un valor de otro tipo cuenta como "sin ajuste": nunca bloquea el agente por error.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.app_setting import AppSetting


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:  # noqa: ANN401
    row = await db.get(AppSetting, key)
    return default if row is None else row.value


async def agent_enabled(db: AsyncSession) -> bool:
    value = await get_setting(db, "agent.enabled", True)
    return value if isinstance(value, bool) else True


async def role_quota(db: AsyncSession, role: str) -> dict[str, int]:
    """Límites de un rol (`runs_per_day`, `tokens_per_day`). Ausente = sin límite."""
    quotas = await get_setting(db, "quotas", {})
    limits = quotas.get(role) if isinstance(quotas, dict) else None
    if not isinstance(limits, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("runs_per_day", "tokens_per_day"):
        value = limits.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    return result


async def starters(db: AsyncSession, mode: str, locale: str) -> list[str]:
    data = await get_setting(db, "starters", {})
    by_locale = data.get(mode) if isinstance(data, dict) else None
    texts = by_locale.get(locale) if isinstance(by_locale, dict) else None
    if not isinstance(texts, list):
        return []
    return [str(text).strip() for text in texts if str(text).strip()]


__all__ = ["agent_enabled", "get_setting", "role_quota", "starters"]
