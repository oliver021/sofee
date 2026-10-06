import httpx
import pytest
import respx

from tests.conftest import csrf_from_client
from tests.helpers import authed_client

API_URL = "https://api.test/v1"


async def _create_provider(client, **overrides):
    payload = {"name": "DeepInfra prod", "kind": "deepinfra", **overrides}
    resp = await client.post(
        "/api/v1/admin/providers",
        json=payload,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- RBAC ----------------------------------------------------------------

async def test_providers_admin_requires_admin(client):
    await authed_client(client, role="regular")
    resp = await client.get("/api/v1/admin/providers")
    assert resp.status_code == 403


async def test_providers_admin_401_without_auth(client):
    resp = await client.get("/api/v1/admin/providers")
    assert resp.status_code == 401


async def test_create_provider_requires_admin(client):
    await authed_client(client, role="regular")
    resp = await client.post(
        "/api/v1/admin/providers",
        json={"name": "x", "kind": "deepinfra"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 403


# --- CRUD -----------------------------------------------------------------

async def test_create_provider(client):
    await authed_client(client)
    provider = await _create_provider(client, name="DeepInfra prod")
    assert provider["kind"] == "deepinfra"
    assert provider["is_enabled"] is True
    assert provider["credential_last_four"] is None


async def test_create_provider_with_initial_key_never_exposes_secret(client):
    await authed_client(client)
    resp = await client.post(
        "/api/v1/admin/providers",
        json={
            "name": "DeepInfra prod",
            "kind": "deepinfra",
            "initial_api_key": "sk-super-secret-9123",
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "sk-super-secret-9123" not in resp.text
    assert body["credential_last_four"] == "9123"


async def test_create_duplicate_name_conflict(client):
    await authed_client(client)
    await _create_provider(client, name="DeepInfra prod")
    resp = await client.post(
        "/api/v1/admin/providers",
        json={"name": "DeepInfra prod", "kind": "deepinfra"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 409


async def test_list_providers(client):
    await authed_client(client)
    await _create_provider(client, name="A1")
    await _create_provider(client, name="B2", kind="openai_compatible", base_url="https://x")
    resp = await client.get("/api/v1/admin/providers")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == sorted(names)


async def test_get_provider(client):
    await authed_client(client)
    provider = await _create_provider(client, name="DeepInfra prod")
    resp = await client.get(f"/api/v1/admin/providers/{provider['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "DeepInfra prod"


async def test_get_provider_404(client):
    await authed_client(client)
    resp = await client.get("/api/v1/admin/providers/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_patch_provider(client):
    await authed_client(client)
    provider = await _create_provider(client, name="DeepInfra prod")
    resp = await client.patch(
        f"/api/v1/admin/providers/{provider['id']}",
        json={"is_enabled": False, "base_url": "https://override"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_enabled"] is False
    assert body["base_url"] == "https://override"


async def test_patch_duplicate_name_conflict(client):
    await authed_client(client)
    p1 = await _create_provider(client, name="A1")
    await _create_provider(client, name="B2")
    resp = await client.patch(
        f"/api/v1/admin/providers/{p1['id']}",
        json={"name": "B2"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 409


async def test_delete_provider(client):
    await authed_client(client)
    provider = await _create_provider(client, name="DeepInfra prod")
    resp = await client.delete(
        f"/api/v1/admin/providers/{provider['id']}",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/admin/providers/{provider['id']}")
    assert resp.status_code == 404


# --- Credenciales ---------------------------------------------------------

async def test_rotate_credential(client):
    await authed_client(client)
    provider = await _create_provider(client, name="DeepInfra prod")
    provider_id = provider["id"]

    resp = await client.post(
        f"/api/v1/admin/providers/{provider_id}/credentials",
        json={"api_key": "sk-first-key-0001"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    first = resp.json()
    assert "sk-first-key-0001" not in resp.text
    assert first["credential"]["last_four"] == "0001"
    assert first["previous_last_four"] is None

    resp = await client.post(
        f"/api/v1/admin/providers/{provider_id}/credentials",
        json={"api_key": "sk-second-0002"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    second = resp.json()
    assert second["previous_last_four"] == "0001"

    resp = await client.get(f"/api/v1/admin/providers/{provider_id}/credentials")
    creds = resp.json()
    assert len(creds) == 2
    active = [c for c in creds if c["is_active"]]
    assert len(active) == 1
    assert active[0]["last_four"] == "0002"
    assert all("sk-" not in json for json in [resp.text])


async def test_openai_compatible_provider_touches_secret_for_provider(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="NyX", kind="openai_compatible", base_url=API_URL,
        initial_api_key="sk-rot-secret-77",
    )
    resp = await client.get(f"/api/v1/admin/providers/{provider['id']}")
    assert resp.status_code == 200
    assert "sk-rot-secret-77" not in resp.text
    assert resp.json()["credential_last_four"] == "t-77"


# --- Test de conexión -----------------------------------------------------

@respx.mock
async def test_provider_test_connection_ok_and_uses_decrypted_secret(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra",
        initial_api_key="sk-secret-4422",
    )
    route = respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]}
        )
    )
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/test",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model_count"] == 3
    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-secret-4422"
    assert "Bearer sk-secret-4422" not in resp.text


@respx.mock
async def test_provider_test_connection_failure(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(502)
    )
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/test",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["model_count"] == 0


@respx.mock
async def test_provider_test_connection_network_error(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        side_effect=httpx.ConnectError("boom")
    )
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/test",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


async def test_openai_compatible_without_base_url_test_fails(client):
    await authed_client(client)
    provider = await _create_provider(client, name="NoURL", kind="openai_compatible")
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/test",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "base_url" in resp.json()["message"]


# --- Modelos --------------------------------------------------------------

@respx.mock
async def test_sync_models_creates_and_is_idempotent(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    remote = {"data": [{"id": "model-a"}, {"id": "model-b"}, {"id": "model-c"}]}
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(200, json=remote)
    )
    url = f"/api/v1/admin/providers/{provider['id']}/models/sync"
    csrf_headers = {"X-CSRF-Token": csrf_from_client(client)}

    resp = await client.post(url, headers=csrf_headers)
    assert resp.status_code == 200
    first = resp.json()
    assert first["created"] == 3
    assert first["already_exists"] == 0
    assert first["total"] == 3

    resp = await client.post(url, headers=csrf_headers)
    second = resp.json()
    assert second["created"] == 0
    assert second["already_exists"] == 3


@respx.mock
async def test_sync_models_remote_error_502(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(500)
    )
    resp = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/models/sync",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 502


@respx.mock
async def test_toggle_model(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "model-a"}]})
    )
    sync = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/models/sync",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    model = sync.json()["models"][0]

    resp = await client.patch(
        f"/api/v1/admin/providers/{provider['id']}/models/{model['id']}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False


@respx.mock
async def test_toggle_model_404_wrong_provider(client):
    await authed_client(client)
    provider = await _create_provider(
        client, name="DeepInfra prod", kind="deepinfra", initial_api_key="sk-x"
    )
    other = await _create_provider(client, name="Other", kind="deepinfra")
    respx.get("https://api.deepinfra.com/v1/openai/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "model-a"}]})
    )
    sync = await client.post(
        f"/api/v1/admin/providers/{provider['id']}/models/sync",
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    model = sync.json()["models"][0]
    resp = await client.patch(
        f"/api/v1/admin/providers/{other['id']}/models/{model['id']}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 404