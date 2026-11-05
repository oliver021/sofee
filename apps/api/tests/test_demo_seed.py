"""Siembra de la demo (`seed-demo`): idempotente, sin red y sin secretos en el repositorio.

El proveedor y la prueba de herramientas son falsos. Las claves de estos tests son valores de prueba
que solo existen dentro del test.
"""

import re

import pytest
from sqlalchemy import func, select

from app.agent.persistence import get_agent_storage
from app.agent.probe import NO_TOOL_CALL, SUPPORTS, ProbeResult
from app.db import async_session_factory
from app.demo_seed import (
    ADMIN_EMAIL,
    DEMO_KB_DIR,
    DEMO_KB_DIRS,
    DEMO_STARTERS,
    USER_EMAIL,
    DemoSeedError,
    seed_demo,
)
from app.models.agent import AgentProfile
from app.models.app_setting import AppSetting
from app.models.catalog import ModelCatalogBinding, ModelCatalogEntry
from app.models.integration import IntegrationCredential
from app.models.kb import KbDocument
from app.models.provider import Provider, ProviderModel
from app.models.user import User

PASSWORD_ENV = {
    "SOFEE_DEMO_ADMIN_PASSWORD": "clave-admin-de-prueba",
    "SOFEE_DEMO_USER_PASSWORD": "clave-usuario-de-prueba",
}
PROVIDER_ENV = {
    "SOFEE_DEMO_PROVIDER_KIND": "deepinfra",
    "SOFEE_DEMO_API_KEY": "clave-proveedor-de-prueba",
    "SOFEE_DEMO_MAIN_MODEL": "modelo/principal-demo",
    "SOFEE_DEMO_WORKER_MODEL": "modelo/respaldo-demo",
    "SOFEE_DEMO_CONTEXT_WINDOW": "64000",
    "SOFEE_DEMO_TAVILY_API_KEY": "clave-tavily-de-prueba",
}


def _demo_files():
    return sorted(DEMO_KB_DIR.glob("*.md"))


async def _count(model) -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _fake_probe_factory(verdicts: dict[str, str], calls: list[str]):
    async def probe(provider, model, api_key):
        calls.append(model.model_id)
        return ProbeResult(verdicts[model.model_id], "prueba falsa")

    return probe


def test_demo_documents_are_real_markdown_with_a_heading_each():
    files = _demo_files()
    assert 12 <= len(files) <= 15
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# "), path.name
        assert len(text.split()) >= 150, path.name


def test_starters_have_three_questions_per_mode_and_language():
    for mode in ("learn", "research", "explore"):
        assert set(DEMO_STARTERS[mode]) == {"es", "en"}
        for texts in DEMO_STARTERS[mode].values():
            assert len(texts) == 3


async def test_seed_without_provider_creates_users_knowledge_profiles_and_starters(client):
    store = get_agent_storage().store
    result = await seed_demo(store, env=PASSWORD_ENV)

    assert result.generated_passwords == {}  # vinieron del entorno: no se devuelven
    assert result.kb_documents == len(_demo_files())
    assert sorted(result.profiles_created) == ["explore", "learn", "research"]
    assert result.starters_set is True
    assert result.catalog_slug is None and result.probes == {}
    assert any("SOFEE_DEMO_PROVIDER_KIND" in note for note in result.notes)

    async with async_session_factory() as db:
        emails = set((await db.execute(select(User.email))).scalars())
        assert emails == {ADMIN_EMAIL, USER_EMAIL}
        active = (
            await db.execute(select(AgentProfile.mode, AgentProfile.version).where(AgentProfile.is_active.is_(True)))
        ).all()
        assert sorted(active) == [("explore", 1), ("learn", 1), ("research", 1)]
    assert await _count(ModelCatalogEntry) == 0
    assert await _count(Provider) == 0

    # El agente lee /kb/ del store, no la BD: cada documento tiene su copia.
    item = store.get(("kb",), "/deploying-a-service.md")
    assert item is not None and item.value["content"].startswith("# How a service is deployed")

    # Las preguntas llegan al cliente por el endpoint real, con la cuenta de la demo.
    login = await client.post("/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD_ENV["SOFEE_DEMO_USER_PASSWORD"]})
    assert login.status_code == 200, login.text
    starters = await client.get("/api/v1/starters", params={"mode": "learn", "locale": "es"})
    assert [item["text"] for item in starters.json()] == DEMO_STARTERS["learn"]["es"]


async def test_generated_passwords_are_returned_once_and_work_for_login(client):
    store = get_agent_storage().store
    result = await seed_demo(store, env={})
    assert set(result.generated_passwords) == {ADMIN_EMAIL, USER_EMAIL}
    assert all(len(password) >= 16 for password in result.generated_passwords.values())

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": USER_EMAIL, "password": result.generated_passwords[USER_EMAIL]},
    )
    assert login.status_code == 200, login.text


async def test_second_run_changes_nothing(client):
    store = get_agent_storage().store
    first = await seed_demo(store, env=PASSWORD_ENV)
    second = await seed_demo(store, env=PASSWORD_ENV)

    assert second.generated_passwords == {}
    assert second.kb_documents == first.kb_documents
    assert second.profiles_created == [] and second.starters_set is False
    assert await _count(User) == 2
    assert await _count(KbDocument) == len(_demo_files())
    assert await _count(AgentProfile) == 3
    async with async_session_factory() as db:
        assert (await db.execute(select(func.count()).select_from(AppSetting).where(AppSetting.key == "starters"))).scalar_one() == 1


async def test_a_document_the_admin_retired_stays_retired_and_out_of_the_store(client):
    store = get_agent_storage().store
    await seed_demo(store, env=PASSWORD_ENV)
    async with async_session_factory() as db:
        document = (
            await db.execute(select(KbDocument).where(KbDocument.slug == "glossary"))
        ).scalar_one()
        document.is_enabled = False
        await db.commit()

    await seed_demo(store, env=PASSWORD_ENV)

    assert store.get(("kb",), "/glossary.md") is None
    async with async_session_factory() as db:
        assert (await db.get(KbDocument, document.id)).is_enabled is False


async def test_provider_env_creates_sofee_pro_and_takes_capabilities_from_the_probe(client):
    store = get_agent_storage().store
    calls: list[str] = []
    probe = await _fake_probe_factory(
        {"modelo/principal-demo": SUPPORTS, "modelo/respaldo-demo": SUPPORTS}, calls
    )
    result = await seed_demo(store, env={**PASSWORD_ENV, **PROVIDER_ENV}, probe=probe)

    assert result.catalog_slug == "pro"
    assert result.probes == {"modelo/principal-demo": SUPPORTS, "modelo/respaldo-demo": SUPPORTS}
    assert result.tavily_configured is True
    assert calls == ["modelo/principal-demo", "modelo/respaldo-demo"]

    async with async_session_factory() as db:
        entry = (await db.execute(select(ModelCatalogEntry).where(ModelCatalogEntry.slug == "pro"))).scalar_one()
        assert entry.display_name == "Sofee Pro"
        bindings = (
            await db.execute(
                select(ModelCatalogBinding.priority, ProviderModel.model_id, ProviderModel.supports_tools, ProviderModel.context_window)
                .join(ProviderModel, ProviderModel.id == ModelCatalogBinding.provider_model_id)
                .where(ModelCatalogBinding.catalog_entry_id == entry.id)
                .order_by(ModelCatalogBinding.priority)
            )
        ).all()
        assert bindings == [
            (0, "modelo/principal-demo", True, 64000),
            (1, "modelo/respaldo-demo", True, 64000),
        ]
        credential = (
            await db.execute(select(IntegrationCredential).where(IntegrationCredential.kind == "tavily"))
        ).scalar_one()
        assert credential.is_active is True

    catalog = await client.get("/api/v1/catalog")  # sin sesión no hay catálogo: se hace como usuario
    assert catalog.status_code == 401
    login = await client.post("/api/v1/auth/login", json={"email": USER_EMAIL, "password": PASSWORD_ENV["SOFEE_DEMO_USER_PASSWORD"]})
    assert login.status_code == 200, login.text
    catalog = await client.get("/api/v1/catalog")
    pro = next(entry for entry in catalog.json() if entry["slug"] == "pro")
    assert pro["agent_ready"] is True and pro["context_window"] == 64000


async def test_a_model_that_refuses_tools_keeps_the_entry_out_of_agent_mode(client):
    store = get_agent_storage().store
    calls: list[str] = []
    probe = await _fake_probe_factory(
        {"modelo/principal-demo": SUPPORTS, "modelo/respaldo-demo": NO_TOOL_CALL}, calls
    )
    result = await seed_demo(store, env={**PASSWORD_ENV, **PROVIDER_ENV}, probe=probe)
    assert result.probes["modelo/respaldo-demo"] == NO_TOOL_CALL

    async with async_session_factory() as db:
        worker = (
            await db.execute(select(ProviderModel).where(ProviderModel.model_id == "modelo/respaldo-demo"))
        ).scalar_one()
        assert worker.supports_tools is False

    # Una segunda pasada no vuelve a probar: la aptitud ya está verificada.
    again = await seed_demo(store, env={**PASSWORD_ENV, **PROVIDER_ENV}, probe=probe)
    assert again.probes == {"modelo/principal-demo": "already_verified", "modelo/respaldo-demo": "already_verified"}
    assert len(calls) == 2


async def test_incomplete_provider_settings_fail_before_anything_is_written():
    store = get_agent_storage().store
    with pytest.raises(DemoSeedError, match="SOFEE_DEMO_API_KEY"):
        await seed_demo(store, env={"SOFEE_DEMO_PROVIDER_KIND": "deepinfra", "SOFEE_DEMO_MAIN_MODEL": "modelo"})
    assert await _count(User) == 0
    assert await _count(KbDocument) == 0


async def test_unknown_provider_kind_and_missing_base_url_are_rejected():
    store = get_agent_storage().store
    with pytest.raises(DemoSeedError, match="SOFEE_DEMO_PROVIDER_KIND"):
        await seed_demo(store, env={"SOFEE_DEMO_PROVIDER_KIND": "otro", "SOFEE_DEMO_API_KEY": "k", "SOFEE_DEMO_MAIN_MODEL": "m"})
    with pytest.raises(DemoSeedError, match="SOFEE_DEMO_BASE_URL"):
        await seed_demo(
            store,
            env={"SOFEE_DEMO_PROVIDER_KIND": "openai_compatible", "SOFEE_DEMO_API_KEY": "k", "SOFEE_DEMO_MAIN_MODEL": "m"},
        )


async def test_the_knowledge_base_can_be_seeded_in_spanish_and_rejects_unknown_locales(client):
    store = get_agent_storage().store
    result = await seed_demo(store, env={**PASSWORD_ENV, "SOFEE_DEMO_KB_LOCALE": "es"})
    assert result.kb_documents == len(sorted(DEMO_KB_DIRS["es"].glob("*.md")))
    item = store.get(("kb",), "/despliegue-de-un-servicio.md")
    assert item is not None and item.value["content"].startswith("# Cómo se despliega")

    with pytest.raises(DemoSeedError, match="SOFEE_DEMO_KB_LOCALE"):
        await seed_demo(store, env={**PASSWORD_ENV, "SOFEE_DEMO_KB_LOCALE": "fr"})


def test_both_knowledge_bases_have_the_same_documents_and_no_dangling_links():
    english = {path.name for path in DEMO_KB_DIRS["en"].glob("*.md")}
    spanish = {path.name for path in DEMO_KB_DIRS["es"].glob("*.md")}
    assert len(english) == len(spanish) == 14
    for path in DEMO_KB_DIRS["en"].glob("*.md"):
        for link in re.findall(r"\]\(([^)#]+\.md)\)", path.read_text()):
            assert link in english, f"{path.name} links to a missing document: {link}"
