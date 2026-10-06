from app.db import async_session_factory
from app.models.catalog import ModelCatalogBinding, ModelCatalogEntry
from app.models.provider import Provider, ProviderKind, ProviderModel
from app.services.providers import create_credential
from tests.helpers import authed_client


async def _seed_bound_entry(
    *, slug="fast", is_enabled=True, provider_enabled=True, with_credential=True
):
    async with async_session_factory() as db:
        provider = Provider(
            name=f"DeepInfra-{slug}", kind=ProviderKind.deepinfra, is_enabled=provider_enabled
        )
        db.add(provider)
        await db.flush()
        if with_credential:
            await create_credential(db, provider.id, "sk-x", None)
        model = ProviderModel(
            provider_id=provider.id, model_id="meta-llama/x", display_name="Llama", is_enabled=True
        )
        db.add(model)
        await db.flush()
        entry = ModelCatalogEntry(
            slug=slug, display_name="Rápido", category="rapido", is_enabled=is_enabled
        )
        db.add(entry)
        await db.flush()
        binding = ModelCatalogBinding(catalog_entry_id=entry.id, provider_model_id=model.id, priority=0)
        db.add(binding)
        await db.commit()
        return entry.id, provider.id, model.id


async def test_catalog_requires_auth(client):
    resp = await client.get("/api/v1/catalog")
    assert resp.status_code == 401


async def test_catalog_excludes_disabled_entries(client):
    await authed_client(client, role="regular")
    await _seed_bound_entry(slug="visible", is_enabled=True)
    await _seed_bound_entry(slug="hidden", is_enabled=False)

    resp = await client.get("/api/v1/catalog")
    assert resp.status_code == 200
    slugs = [e["slug"] for e in resp.json()]
    assert "visible" in slugs
    assert "hidden" not in slugs


async def test_catalog_entry_shape_hides_provider_details(client):
    await authed_client(client, role="regular")
    await _seed_bound_entry()

    resp = await client.get("/api/v1/catalog")
    body = resp.json()
    assert len(body) == 1
    entry = body[0]
    assert set(entry.keys()) == {
        "id",
        "slug",
        "display_name",
        "description",
        "category",
        "is_available",
    }
    assert "DeepInfra" not in resp.text
    assert "meta-llama/x" not in resp.text


async def test_catalog_is_available_true_with_healthy_binding(client):
    await authed_client(client, role="regular")
    await _seed_bound_entry()
    resp = await client.get("/api/v1/catalog")
    assert resp.json()[0]["is_available"] is True


async def test_catalog_is_available_false_without_credential(client):
    await authed_client(client, role="regular")
    await _seed_bound_entry(with_credential=False)
    resp = await client.get("/api/v1/catalog")
    assert resp.json()[0]["is_available"] is False


async def test_catalog_is_available_false_when_provider_disabled(client):
    await authed_client(client, role="regular")
    await _seed_bound_entry(provider_enabled=False)
    resp = await client.get("/api/v1/catalog")
    assert resp.json()[0]["is_available"] is False
