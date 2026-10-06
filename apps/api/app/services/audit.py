import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditLog

_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "api_key",
    "cookie",
}


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Registra un evento de auditoría sin commitear: la transacción la cierra la ruta."""
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        data=data,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Los headers por defecto de un provider pueden llevar secretos inline."""
    return {
        key: ("***" if key.lower() in _SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }


__all__ = ["redact_headers", "write_audit"]