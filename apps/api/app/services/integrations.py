"""Credenciales de integraciones externas (hoy: Tavily), cifradas como las de los providers."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import decrypt_secret, encrypt_secret, last_four
from ..models.integration import IntegrationCredential

TAVILY = "tavily"


async def active_credential(db: AsyncSession, kind: str) -> IntegrationCredential | None:
    return (
        await db.execute(
            select(IntegrationCredential).where(
                IntegrationCredential.kind == kind,
                IntegrationCredential.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def is_configured(db: AsyncSession, kind: str) -> bool:
    return (await active_credential(db, kind)) is not None


async def active_secret(db: AsyncSession, kind: str) -> str | None:
    """Clave descifrada, solo para llamar a la API. Nunca se guarda en el estado del agente."""
    credential = await active_credential(db, kind)
    if credential is None:
        return None
    return decrypt_secret(credential.secret_ciphertext)


async def store_credential(
    db: AsyncSession, kind: str, secret: str, actor_id: uuid.UUID | None
) -> IntegrationCredential:
    """Activa una clave nueva y desactiva la anterior de ese tipo. No commitea."""
    await db.execute(
        update(IntegrationCredential)
        .where(IntegrationCredential.kind == kind, IntegrationCredential.is_active.is_(True))
        .values(is_active=False)
    )
    credential = IntegrationCredential(
        kind=kind,
        secret_ciphertext=encrypt_secret(secret),
        last_four=last_four(secret),
        is_active=True,
        created_by=actor_id,
    )
    db.add(credential)
    await db.flush()
    return credential


__all__ = ["TAVILY", "active_credential", "active_secret", "is_configured", "store_credential"]
