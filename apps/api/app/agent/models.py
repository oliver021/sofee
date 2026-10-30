"""Catálogo -> modelo de chat de LangChain para el agente.

Usa `ChatOpenAI` contra el `base_url` que resuelve el registro de providers: los
cuatro `kind` son compatibles con OpenAI. La key se descifra aquí, en el momento
de resolver, y nunca se guarda ni se registra.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.providers.registry import resolved_base_url
from ..models.catalog import ModelCatalogEntry
from ..models.provider import Provider, ProviderModel
from ..services.catalog import bindings_with_availability, is_agent_ready
from ..services.providers import resolve_provider_secret

DEFAULT_CONTEXT_WINDOW = 32_000


class ModelUnavailable(Exception):
    """Ningún binding del catálogo puede servir al agente ahora mismo."""


@dataclass(frozen=True)
class ResolvedModel:
    chat_model: BaseChatModel
    label: str
    catalog_slug: str
    provider_model_id: uuid.UUID
    context_window: int | None
    input_price: Decimal | None
    output_price: Decimal | None
    # Bindings disponibles restantes, en orden de prioridad: failover en mitad del run.
    fallback_models: tuple[BaseChatModel, ...] = field(default=())


# Fábrica inyectable: en tests devuelve modelos falsos (sin red).
ChatModelFactory = Callable[[Provider, ProviderModel, str], BaseChatModel]


def build_chat_model(provider: Provider, provider_model: ProviderModel, api_key: str) -> BaseChatModel:
    base_url = resolved_base_url(provider.kind, provider.base_url)
    return ChatOpenAI(
        model=provider_model.model_id,
        base_url=base_url,
        api_key=api_key,
        default_headers=provider.default_headers or None,
        # Con base_url propio ChatOpenAI desactiva el usage en streaming; sin él no hay
        # medidor de contexto ni coste.
        stream_usage=True,
        profile={
            "max_input_tokens": provider_model.context_window or DEFAULT_CONTEXT_WINDOW,
            "tool_calling": True,
        },
    )


async def _agent_entry_for(db: AsyncSession, slug: str | None) -> ModelCatalogEntry | None:
    if slug is not None:
        entry = (
            await db.execute(
                select(ModelCatalogEntry).where(
                    ModelCatalogEntry.slug == slug, ModelCatalogEntry.is_enabled.is_(True)
                )
            )
        ).scalar_one_or_none()
        return entry

    entries = (
        await db.execute(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.is_enabled.is_(True))
            .order_by(ModelCatalogEntry.sort_order, ModelCatalogEntry.display_name)
        )
    ).scalars()
    for entry in entries:
        rows = await bindings_with_availability(db, entry.id)
        if is_agent_ready(rows):
            return entry
    return None


async def resolve_chat_model(
    db: AsyncSession,
    slug: str | None,
    *,
    factory: ChatModelFactory | None = None,
) -> ResolvedModel:
    """Elige la entrada del catálogo y construye el modelo primario y sus alternativas.

    `slug=None` toma la primera entrada habilitada y apta para agentes (por `sort_order`).
    Solo cuentan los bindings disponibles y con `supports_tools` verificado.
    """
    build = factory or build_chat_model
    entry = await _agent_entry_for(db, slug)
    if entry is None:
        raise ModelUnavailable("No hay ningún modelo apto para agentes disponible")

    rows = await bindings_with_availability(db, entry.id)
    usable: list[tuple[ProviderModel, Provider]] = []
    for _binding, model, provider, available in rows:
        if available and model.supports_tools is True:
            usable.append((model, provider))

    built: list[tuple[ProviderModel, BaseChatModel]] = []
    for model, provider in usable:
        if resolved_base_url(provider.kind, provider.base_url) is None:
            continue
        api_key = await resolve_provider_secret(db, provider.id)
        if not api_key:
            continue
        built.append((model, build(provider, model, api_key)))

    if not built:
        raise ModelUnavailable(f"El modelo '{entry.slug}' no tiene ningún binding utilizable")

    primary_model, primary_chat = built[0]
    return ResolvedModel(
        chat_model=primary_chat,
        label=entry.display_name,
        catalog_slug=entry.slug,
        provider_model_id=primary_model.id,
        context_window=primary_model.context_window,
        input_price=primary_model.input_price_per_mtok,
        output_price=primary_model.output_price_per_mtok,
        fallback_models=tuple(chat for _, chat in built[1:]),
    )


__all__ = [
    "ChatModelFactory",
    "DEFAULT_CONTEXT_WINDOW",
    "ModelUnavailable",
    "ResolvedModel",
    "build_chat_model",
    "resolve_chat_model",
]
