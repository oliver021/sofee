import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import decrypt_secret, encrypt_secret, last_four
from ..core.providers import ProviderAdapter, ProviderError, build_adapter
from ..models.provider import Provider, ProviderCredential


async def get_active_credential(
    db: AsyncSession, provider_id: uuid.UUID
) -> ProviderCredential | None:
    return (
        await db.execute(
            select(ProviderCredential).where(
                ProviderCredential.provider_id == provider_id,
                ProviderCredential.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def create_credential(
    db: AsyncSession,
    provider_id: uuid.UUID,
    api_key: str,
    actor_id: uuid.UUID | None,
    *,
    deactivate_previous: bool = True,
) -> ProviderCredential:
    if deactivate_previous:
        await db.execute(
            update(ProviderCredential)
            .where(
                ProviderCredential.provider_id == provider_id,
                ProviderCredential.is_active.is_(True),
            )
            .values(is_active=False)
        )
    credential = ProviderCredential(
        provider_id=provider_id,
        secret_ciphertext=encrypt_secret(api_key),
        last_four=last_four(api_key),
        is_active=True,
        created_by=actor_id,
    )
    db.add(credential)
    await db.flush()
    return credential


async def resolve_provider_secret(
    db: AsyncSession, provider_id: uuid.UUID
) -> str | None:
    credential = await get_active_credential(db, provider_id)
    if credential is None:
        return None
    return decrypt_secret(credential.secret_ciphertext)


async def build_adapter_for_provider(
    db: AsyncSession, provider: Provider
) -> ProviderAdapter:
    api_key = await resolve_provider_secret(db, provider.id)
    return build_adapter(
        kind=provider.kind,
        base_url=provider.base_url,
        api_key=api_key,
        default_headers=provider.default_headers,
    )


__all__ = [
    "ProviderError",
    "build_adapter_for_provider",
    "create_credential",
    "get_active_credential",
    "resolve_provider_secret",
]