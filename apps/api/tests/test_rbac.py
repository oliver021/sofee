import pytest

from app.models.user import UserRole
from tests.conftest import csrf_from_client
from tests.helpers import create_user, insert_session, login_through_api

UUID = "00000000-0000-0000-0000-000000000000"

# Todos los endpoints admin existentes: un usuario regular debe recibir 403 (no
# 404), para no filtrar por side-channel qué rutas existen. Un anónimo debe
# recibir 401. Una ruta inexistente debe seguir dando 404 en ambos casos.
ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/admin/users"),
    ("PATCH", f"/api/v1/admin/users/{UUID}"),
    ("GET", f"/api/v1/admin/users/{UUID}/sessions"),
    ("POST", f"/api/v1/admin/users/{UUID}/revoke-sessions"),
    ("DELETE", f"/api/v1/admin/sessions/{UUID}"),
    ("GET", "/api/v1/admin/audit"),
    ("GET", "/api/v1/admin/providers"),
    ("POST", "/api/v1/admin/providers"),
    ("GET", f"/api/v1/admin/providers/{UUID}"),
    ("PATCH", f"/api/v1/admin/providers/{UUID}"),
    ("DELETE", f"/api/v1/admin/providers/{UUID}"),
    ("POST", f"/api/v1/admin/providers/{UUID}/test"),
    ("GET", f"/api/v1/admin/providers/{UUID}/credentials"),
    ("POST", f"/api/v1/admin/providers/{UUID}/credentials"),
    ("GET", f"/api/v1/admin/providers/{UUID}/models"),
    ("POST", f"/api/v1/admin/providers/{UUID}/models/sync"),
    ("PATCH", f"/api/v1/admin/providers/{UUID}/models/{UUID}"),
]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
async def test_admin_endpoint_403_for_regular_user(method, path, client):
    await login_through_api(client)
    resp = await client.request(
        method,
        path,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 403, (method, path)


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
async def test_admin_endpoint_401_without_auth(method, path, client):
    resp = await client.request(method, path)
    assert resp.status_code == 401, (method, path)


async def test_regular_session_cookie_gets_403(client):
    user = await create_user()
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 403


async def test_admin_session_gets_200(client):
    user = await create_user(email="admin@example.com", role=UserRole.admin)
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    users = resp.json()
    assert any(u["email"] == "admin@example.com" for u in users)


async def test_unknown_route_404_for_regular_user(client):
    """Contraste: una ruta que no existe da 404, una admin protegida da 403."""
    await login_through_api(client)
    resp = await client.get("/api/v1/admin/does-not-exist")
    assert resp.status_code == 404


async def test_unknown_route_404_for_anonymous(client):
    resp = await client.get("/api/v1/admin/does-not-exist")
    assert resp.status_code == 404