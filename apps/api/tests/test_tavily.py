"""Clave de Tavily: admin (RBAC, CSRF, cifrado, auditoría), prueba de conexión y cliente HTTP.

Sin red: respx intercepta cada llamada a api.tavily.com y falla si no hay mock.
"""

import httpx
import respx
from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.integration import IntegrationCredential
from app.models.user import UserRole
from app.services.tavily import TAVILY_SEARCH_URL, TavilyError, tavily_search
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user, insert_session

KEY_OLD = "tvly-antigua-0001"
KEY_NEW = "tvly-nueva-4242"
RESULTS = {
    "results": [
        {"title": "FastAPI", "url": "https://fastapi.tiangolo.com/", "content": "Framework web de Python."},
        {"title": "Sin url", "url": "", "content": "se descarta"},
    ]
}


async def _put_key(client, key: str):
    return await client.put(
        "/api/v1/admin/integrations/tavily",
        json={"api_key": key},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


async def test_status_is_unconfigured_until_a_key_is_saved(client):
    await authed_client(client)
    resp = await client.get("/api/v1/admin/integrations/tavily")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False, "last_four": None, "updated_at": None}


async def test_put_stores_only_the_ciphertext_and_replaces_the_previous_key(client):
    await authed_client(client)
    resp = await _put_key(client, KEY_OLD)
    assert resp.status_code == 200, resp.text
    assert resp.json()["configured"] is True and resp.json()["last_four"] == KEY_OLD[-4:]
    await _put_key(client, KEY_NEW)

    status = (await client.get("/api/v1/admin/integrations/tavily")).json()
    assert status["last_four"] == KEY_NEW[-4:]
    assert KEY_NEW not in str(status) and KEY_OLD not in str(status)

    async with async_session_factory() as db:
        rows = (await db.execute(select(IntegrationCredential))).scalars().all()
        assert len(rows) == 2
        active = [row for row in rows if row.is_active]
        assert len(active) == 1 and active[0].last_four == KEY_NEW[-4:]
        for row in rows:
            assert KEY_NEW.encode() not in row.secret_ciphertext
            assert KEY_OLD.encode() not in row.secret_ciphertext
        audit = (await db.execute(select(AuditLog).where(AuditLog.action == "integration.tavily_key_set"))).scalars().all()
        assert len(audit) == 2
        assert all(KEY_NEW not in str(entry.data) and KEY_OLD not in str(entry.data) for entry in audit)


async def test_status_and_put_are_admin_only_and_need_csrf(client):
    user = await create_user(email="regular@example.com", role=UserRole.regular)
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    assert (await client.get("/api/v1/admin/integrations/tavily")).status_code == 403
    assert (await _put_key(client, KEY_NEW)).status_code == 403

    await authed_client(client)
    resp = await client.put("/api/v1/admin/integrations/tavily", json={"api_key": KEY_NEW})
    assert resp.status_code == 403


async def test_test_endpoint_reports_a_missing_key_without_calling_tavily(client):
    await authed_client(client)
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=RESULTS))
        resp = await client.post(
            "/api/v1/admin/integrations/tavily/test",
            headers={"X-CSRF-Token": csrf_from_client(client)},
        )
    assert resp.json() == {"ok": False, "message": "No hay ninguna clave configurada."}
    assert not route.called


async def test_test_endpoint_uses_the_active_key_and_audits_the_outcome(client):
    await authed_client(client)
    await _put_key(client, KEY_NEW)
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    with respx.mock(assert_all_mocked=True) as mock:
        route = mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=RESULTS))
        ok = await client.post("/api/v1/admin/integrations/tavily/test", headers=headers)
    assert ok.json()["ok"] is True
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY_NEW}"

    with respx.mock(assert_all_mocked=True) as mock:
        mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(401, json={"detail": "bad key"}))
        rejected = await client.post("/api/v1/admin/integrations/tavily/test", headers=headers)
    assert rejected.json() == {"ok": False, "message": "Tavily rechazó la clave"}

    with respx.mock(assert_all_mocked=True) as mock:
        mock.post(TAVILY_SEARCH_URL).mock(side_effect=httpx.ConnectError("sin red"))
        offline = await client.post("/api/v1/admin/integrations/tavily/test", headers=headers)
    assert offline.json() == {"ok": False, "message": "No hubo conexión con Tavily"}

    async with async_session_factory() as db:
        audit = (await db.execute(select(AuditLog).where(AuditLog.action == "integration.tavily_tested"))).scalars().all()
    assert [entry.data["ok"] for entry in audit] == [True, False, False]
    assert all(KEY_NEW not in str(entry.data) for entry in audit)


async def test_client_maps_http_failures_to_readable_errors():
    with respx.mock(assert_all_mocked=True) as mock:
        mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(500))
        try:
            await tavily_search(KEY_NEW, "hola", max_results=1)
        except TavilyError as exc:
            assert "500" in str(exc) and KEY_NEW not in str(exc)
        else:  # pragma: no cover
            raise AssertionError("un 500 debe lanzar TavilyError")

    with respx.mock(assert_all_mocked=True) as mock:
        mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=RESULTS))
        results = await tavily_search(KEY_NEW, "fastapi", max_results=3)
    assert [r.url for r in results] == ["https://fastapi.tiangolo.com/"]
