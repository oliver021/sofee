from app.db import async_session_factory
from app.models.provider import Provider, ProviderKind, ProviderModel
from tests.helpers import authed_client, create_user


async def _seed_models(db, provider_id, model_ids):
    for mid in model_ids:
        db.add(
            ProviderModel(
                provider_id=provider_id, model_id=mid, display_name=mid, is_enabled=True
            )
        )
    await db.commit()


async def test_public_models_requires_auth(client):
    resp = await client.get("/api/v1/providers/models")
    assert resp.status_code == 401


async def test_public_models_only_enabled_of_enabled(client):
    await authed_client(client)
    async with async_session_factory() as db:
        enabled_provider = Provider(name="Enabled", kind=ProviderKind.deepinfra, is_enabled=True)
        disabled_provider = Provider(name="Disabled", kind=ProviderKind.deepinfra, is_enabled=False)
        db.add_all([enabled_provider, disabled_provider])
        await db.flush()
        await _seed_models(db, enabled_provider.id, ["model-a", "model-b"])
        disabled_model = ProviderModel(
            provider_id=enabled_provider.id, model_id="model-c", display_name="c", is_enabled=False
        )
        db.add(disabled_model)
        await _seed_models(db, disabled_provider.id, ["model-x"])
        enabled_provider_id = enabled_provider.id

    resp = await client.get("/api/v1/providers/models")
    assert resp.status_code == 200
    models = resp.json()
    ids = [(m["provider_id"], m["model_id"]) for m in models]
    assert (str(enabled_provider_id), "model-a") in ids
    assert (str(enabled_provider_id), "model-b") in ids
    assert (str(enabled_provider_id), "model-c") not in ids  # deshabilitado
    assert all(m["model_id"] != "model-x" for m in models)  # provider deshabilitado
    assert all("api" not in m["model_id"] and "headers" not in m for m in models)


async def test_public_models_exposes_no_credentials_or_urls(client):
    await authed_client(client)
    async with async_session_factory() as db:
        provider = Provider(
            name="SecretProv", kind=ProviderKind.openai_compatible,
            base_url="https://internal-url.example", default_headers={"X-Key": "z"},
        )
        db.add(provider)
        await db.flush()
        await _seed_models(db, provider.id, ["model-a"])
    resp = await client.get("/api/v1/providers/models")
    body = resp.text
    assert "internal-url" not in body
    assert "X-Key" not in body
    assert "z" not in body