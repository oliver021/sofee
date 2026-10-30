import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.catalog import ModelCatalogBinding, ModelCatalogEntry
from ..models.provider import Provider, ProviderCredential, ProviderModel


async def bindings_with_availability(
    db: AsyncSession, entry_id: uuid.UUID
) -> list[tuple[ModelCatalogBinding, ProviderModel, Provider, bool]]:
    """Cada binding de la entrada, con el flag de disponibilidad resuelto.

    Disponible = binding activo, modelo activo, provider activo y con una
    credencial activa. Ordenado por prioridad (0 = primario).
    """
    rows = (
        await db.execute(
            select(ModelCatalogBinding, ProviderModel, Provider)
            .join(ProviderModel, ProviderModel.id == ModelCatalogBinding.provider_model_id)
            .join(Provider, Provider.id == ProviderModel.provider_id)
            .where(ModelCatalogBinding.catalog_entry_id == entry_id)
            .order_by(ModelCatalogBinding.priority, ModelCatalogBinding.created_at)
        )
    ).all()
    if not rows:
        return []

    provider_ids = {provider.id for _, _, provider in rows}
    active_credential_provider_ids = set(
        (
            await db.execute(
                select(ProviderCredential.provider_id)
                .where(
                    ProviderCredential.provider_id.in_(provider_ids),
                    ProviderCredential.is_active.is_(True),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    result = []
    for binding, model, provider in rows:
        available = (
            binding.is_enabled
            and model.is_enabled
            and provider.is_enabled
            and provider.id in active_credential_provider_ids
        )
        result.append((binding, model, provider, available))
    return result


def is_agent_ready(
    rows: list[tuple[ModelCatalogBinding, ProviderModel, Provider, bool]],
) -> bool:
    """Apta para agentes: hay al menos un binding disponible y todos los disponibles admiten tools.

    `supports_tools` es verificado por una prueba real (null o False cuenta como no apto).
    """
    available = [model for _, model, _, ok in rows if ok]
    return bool(available) and all(model.supports_tools is True for model in available)


async def entry_is_available(db: AsyncSession, entry_id: uuid.UUID) -> bool:
    rows = await bindings_with_availability(db, entry_id)
    return any(available for _, _, _, available in rows)


async def resolve_entry(
    db: AsyncSession, entry_id: uuid.UUID
) -> tuple[ProviderModel, Provider] | None:
    """El binding utilizable de mayor prioridad, o None si ninguno lo está."""
    rows = await bindings_with_availability(db, entry_id)
    for _, model, provider, available in rows:
        if available:
            return model, provider
    return None


async def load_entry(db: AsyncSession, entry_id: uuid.UUID) -> ModelCatalogEntry | None:
    return await db.get(ModelCatalogEntry, entry_id)


__all__ = [
    "bindings_with_availability",
    "entry_is_available",
    "is_agent_ready",
    "load_entry",
    "resolve_entry",
]
