from app.db import async_session_factory
from app.models.provider import ProviderModel
from tests.conftest import csrf_from_client
from tests.helpers import authed_client


async def _create_provider(client, **overrides):
    payload = {"name": "DeepInfra prod", "kind": "deepinfra", "initial_api_key": "sk-x", **overrides}
    resp = await client.post(
        "/api/v1/admin/providers",
        json=payload,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_model(provider_id, model_id="model-a", is_enabled=True):
    async with async_session_factory() as db:
        model = ProviderModel(
            provider_id=provider_id, model_id=model_id, display_name=model_id, is_enabled=is_enabled
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model


async def _create_entry(client, **overrides):
    payload = {
        "slug": "fast",
        "display_name": "Rápido",
        "category": "rapido",
        **overrides,
    }
    resp = await client.post(
        "/api/v1/admin/catalog",
        json=payload,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- RBAC / auth -----------------------------------------------------------

async def test_catalog_admin_requires_admin(client):
    await authed_client(client, role="regular")
    resp = await client.get("/api/v1/admin/catalog")
    assert resp.status_code == 403


async def test_catalog_admin_401_without_auth(client):
    resp = await client.get("/api/v1/admin/catalog")
    assert resp.status_code == 401


async def test_create_entry_requires_csrf(client):
    await authed_client(client)
    resp = await client.post(
        "/api/v1/admin/catalog",
        json={"slug": "fast", "display_name": "Rápido", "category": "rapido"},
    )
    assert resp.status_code == 403


# --- CRUD entradas ----------------------------------------------------------

async def test_create_entry_defaults(client):
    await authed_client(client)
    entry = await _create_entry(client)
    assert entry["slug"] == "fast"
    assert entry["is_enabled"] is True
    assert entry["is_available"] is False
    assert entry["bindings"] == []


async def test_create_entry_duplicate_slug_conflicts(client):
    await authed_client(client)
    await _create_entry(client)
    resp = await client.post(
        "/api/v1/admin/catalog",
        json={"slug": "fast", "display_name": "Otro", "category": "rapido"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 409


async def test_update_entry(client):
    await authed_client(client)
    entry = await _create_entry(client)
    resp = await client.patch(
        f"/api/v1/admin/catalog/{entry['id']}",
        json={"display_name": "Rápido v2", "is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "Rápido v2"
    assert body["is_enabled"] is False


async def test_delete_entry(client):
    await authed_client(client)
    entry = await _create_entry(client)
    resp = await client.delete(
        f"/api/v1/admin/catalog/{entry['id']}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/admin/catalog/{entry['id']}")
    assert resp.status_code == 404


async def test_get_entry_404(client):
    await authed_client(client)
    resp = await client.get("/api/v1/admin/catalog/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# --- Bindings ---------------------------------------------------------------

async def test_add_binding_makes_entry_available(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)

    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_available"] is True
    assert len(body["bindings"]) == 1
    binding = body["bindings"][0]
    assert binding["priority"] == 0
    assert binding["provider_name"] == provider["name"]
    assert binding["model_id"] == "model-a"
    assert binding["is_available"] is True


async def test_bindings_auto_increment_priority_and_order(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model_a = await _add_model(provider["id"], "model-a")
    model_b = await _add_model(provider["id"], "model-b")
    entry = await _create_entry(client)

    await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model_a.id)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model_b.id)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    bindings = resp.json()["bindings"]
    assert [b["priority"] for b in bindings] == [0, 1]
    assert [b["model_id"] for b in bindings] == ["model-a", "model-b"]


async def test_duplicate_binding_conflicts(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)
    await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 409


async def test_add_binding_unknown_model_404(client):
    await authed_client(client)
    entry = await _create_entry(client)
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": "00000000-0000-0000-0000-000000000000"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404


async def test_disable_primary_binding_falls_back(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model_a = await _add_model(provider["id"], "model-a")
    model_b = await _add_model(provider["id"], "model-b")
    entry = await _create_entry(client)
    csrf = csrf_from_client(client)

    await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model_a.id)},
        headers={"X-CSRF-Token": csrf},
    )
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model_b.id)},
        headers={"X-CSRF-Token": csrf},
    )
    primary_id = resp.json()["bindings"][0]["id"]

    resp = await client.patch(
        f"/api/v1/admin/catalog/{entry['id']}/bindings/{primary_id}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_available"] is True  # el fallback sigue sirviendo
    assert body["bindings"][0]["is_available"] is False
    assert body["bindings"][1]["is_available"] is True


async def test_disable_all_bindings_makes_entry_unavailable(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)
    csrf = csrf_from_client(client)
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf},
    )
    binding_id = resp.json()["bindings"][0]["id"]

    resp = await client.patch(
        f"/api/v1/admin/catalog/{entry['id']}/bindings/{binding_id}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.json()["is_available"] is False


async def test_remove_binding(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)
    csrf = csrf_from_client(client)
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf},
    )
    binding_id = resp.json()["bindings"][0]["id"]

    resp = await client.delete(
        f"/api/v1/admin/catalog/{entry['id']}/bindings/{binding_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["bindings"] == []


async def test_binding_wrong_entry_404(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)
    other_entry = await _create_entry(client, slug="other", display_name="Otro")
    csrf = csrf_from_client(client)
    resp = await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf},
    )
    binding_id = resp.json()["bindings"][0]["id"]

    resp = await client.patch(
        f"/api/v1/admin/catalog/{other_entry['id']}/bindings/{binding_id}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 404


async def test_provider_disabled_makes_binding_unavailable(client):
    await authed_client(client)
    provider = await _create_provider(client)
    model = await _add_model(provider["id"])
    entry = await _create_entry(client)
    csrf = csrf_from_client(client)
    await client.post(
        f"/api/v1/admin/catalog/{entry['id']}/bindings",
        json={"provider_model_id": str(model.id)},
        headers={"X-CSRF-Token": csrf},
    )

    await client.patch(
        f"/api/v1/admin/providers/{provider['id']}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )

    resp = await client.get(f"/api/v1/admin/catalog/{entry['id']}")
    assert resp.json()["is_available"] is False
