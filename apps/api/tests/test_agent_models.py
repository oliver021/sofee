import uuid
from decimal import Decimal

import pytest
from langchain_openai import ChatOpenAI

from app.agent.models import DEFAULT_CONTEXT_WINDOW, ModelUnavailable, build_chat_model, resolve_chat_model
from app.db import async_session_factory
from app.models.catalog import ModelCatalogBinding, ModelCatalogEntry
from app.models.provider import Provider, ProviderKind, ProviderModel
from app.services.providers import create_credential
from tests.agent_fakes import ScriptedChatModel
from tests.helpers import authed_client


async def _entry(db, *, slug, sort_order=0, is_enabled=True) -> ModelCatalogEntry:
    entry = ModelCatalogEntry(
        slug=slug,
        display_name=f"Modelo {slug}",
        category="agente",
        is_enabled=is_enabled,
        sort_order=sort_order,
    )
    db.add(entry)
    await db.flush()
    return entry


async def _model(db, provider, *, model_id, supports_tools, context_window=None):
    model = ProviderModel(
        provider_id=provider.id,
        model_id=model_id,
        display_name=model_id,
        is_enabled=True,
        supports_tools=supports_tools,
        context_window=context_window,
        input_price_per_mtok=Decimal("1.5"),
        output_price_per_mtok=Decimal("6"),
    )
    db.add(model)
    await db.flush()
    return model


async def _bind(db, entry, model, priority):
    db.add(ModelCatalogBinding(catalog_entry_id=entry.id, provider_model_id=model.id, priority=priority))
    await db.flush()


async def _provider(db, name, *, with_credential=True, kind=ProviderKind.deepinfra) -> Provider:
    provider = Provider(name=name, kind=kind, is_enabled=True)
    db.add(provider)
    await db.flush()
    if with_credential:
        await create_credential(db, provider.id, f"sk-{name}-secret", None)
    return provider


def _factory(provider, model, api_key):  # noqa: ARG001
    return ScriptedChatModel(script=[])


async def test_slug_none_picks_first_agent_ready_entry_by_sort_order():
    async with async_session_factory() as db:
        provider = await _provider(db, "p1")
        not_tools = await _entry(db, slug="no-tools", sort_order=0)
        await _bind(db, not_tools, await _model(db, provider, model_id="m-old", supports_tools=False), 0)
        ready_late = await _entry(db, slug="ready-late", sort_order=5)
        await _bind(db, ready_late, await _model(db, provider, model_id="m-late", supports_tools=True), 0)
        ready_early = await _entry(db, slug="ready-early", sort_order=1)
        await _bind(db, ready_early, await _model(db, provider, model_id="m-early", supports_tools=True), 0)
        await db.commit()

    async with async_session_factory() as db:
        resolved = await resolve_chat_model(db, None, factory=_factory)
    assert resolved.catalog_slug == "ready-early"
    assert resolved.label == "Modelo ready-early"


async def test_supports_tools_none_is_not_agent_ready():
    async with async_session_factory() as db:
        provider = await _provider(db, "p2")
        entry = await _entry(db, slug="untested")
        await _bind(db, entry, await _model(db, provider, model_id="m-untested", supports_tools=None), 0)
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ModelUnavailable):
            await resolve_chat_model(db, None, factory=_factory)


async def test_slug_unknown_or_disabled_raises_unavailable():
    async with async_session_factory() as db:
        provider = await _provider(db, "p3")
        entry = await _entry(db, slug="apagado", is_enabled=False)
        await _bind(db, entry, await _model(db, provider, model_id="m-x", supports_tools=True), 0)
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ModelUnavailable):
            await resolve_chat_model(db, "apagado", factory=_factory)
        with pytest.raises(ModelUnavailable):
            await resolve_chat_model(db, "no-existe", factory=_factory)


async def test_entry_without_credential_is_unavailable():
    async with async_session_factory() as db:
        provider = await _provider(db, "p4", with_credential=False)
        entry = await _entry(db, slug="sin-key")
        await _bind(db, entry, await _model(db, provider, model_id="m-y", supports_tools=True), 0)
        await db.commit()

    async with async_session_factory() as db:
        with pytest.raises(ModelUnavailable):
            await resolve_chat_model(db, "sin-key", factory=_factory)


async def test_fallbacks_are_remaining_usable_bindings_in_priority_order():
    seen = []

    def record(provider, model, api_key):
        seen.append((model.model_id, api_key))
        return ScriptedChatModel(script=[])

    async with async_session_factory() as db:
        provider = await _provider(db, "p5")
        other = await _provider(db, "p6")
        entry = await _entry(db, slug="rapido")
        primary = await _model(db, provider, model_id="primario", supports_tools=True, context_window=64_000)
        secondary = await _model(db, other, model_id="secundario", supports_tools=True)
        skipped = await _model(db, other, model_id="sin-tools", supports_tools=False)
        await _bind(db, entry, primary, 0)
        await _bind(db, entry, skipped, 1)
        await _bind(db, entry, secondary, 2)
        await db.commit()

    async with async_session_factory() as db:
        resolved = await resolve_chat_model(db, "rapido", factory=record)

    assert [model_id for model_id, _ in seen] == ["primario", "secundario"]
    assert resolved.context_window == 64_000
    assert len(resolved.fallback_models) == 1
    assert resolved.input_price == Decimal("1.5")
    assert resolved.provider_model_id is not None and isinstance(resolved.provider_model_id, uuid.UUID)


async def test_build_chat_model_uses_usage_streaming_and_profile():
    async with async_session_factory() as db:
        provider = await _provider(db, "p7", kind=ProviderKind.vercel_gateway)
        model = await _model(db, provider, model_id="meta/llama", supports_tools=True, context_window=128_000)
        await db.commit()
        model_row = model

    chat = build_chat_model(provider, model_row, "sk-test")
    assert isinstance(chat, ChatOpenAI)
    assert chat.stream_usage is True
    assert chat.profile == {"max_input_tokens": 128_000, "tool_calling": True}
    assert str(chat.openai_api_base).startswith("https://ai-gateway.vercel.sh")


async def test_build_chat_model_falls_back_to_default_context_window():
    async with async_session_factory() as db:
        provider = await _provider(db, "p8")
        model = await _model(db, provider, model_id="m-sin-ventana", supports_tools=True)
        await db.commit()
        model_row = model
    chat = build_chat_model(provider, model_row, "sk-test")
    assert chat.profile["max_input_tokens"] == DEFAULT_CONTEXT_WINDOW


async def test_public_catalog_reports_agent_ready_and_context_window(client):
    await authed_client(client, role="regular")
    async with async_session_factory() as db:
        provider = await _provider(db, "p9")
        ready = await _entry(db, slug="listo", sort_order=0)
        await _bind(db, ready, await _model(db, provider, model_id="m-ready", supports_tools=True, context_window=40_000), 0)
        untested = await _entry(db, slug="sin-probar", sort_order=1)
        await _bind(db, untested, await _model(db, provider, model_id="m-untested", supports_tools=None), 0)
        await db.commit()

    resp = await client.get("/api/v1/catalog")
    assert resp.status_code == 200
    by_slug = {entry["slug"]: entry for entry in resp.json()}
    assert by_slug["listo"]["agent_ready"] is True
    assert by_slug["listo"]["context_window"] == 40_000
    assert by_slug["sin-probar"]["agent_ready"] is False
    assert by_slug["sin-probar"]["is_available"] is True
    assert by_slug["sin-probar"]["context_window"] is None
