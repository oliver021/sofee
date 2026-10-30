"""Aptitud para agentes en el catálogo: capacidades de los modelos, "Probar como agente" y auditoría.

La prueba habla con el provider mockeado con respx: sin red. La clave del provider no debe aparecer
nunca en la respuesta ni en la auditoría.
"""

import uuid
from decimal import Decimal

import httpx
import respx
from sqlalchemy import select

from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.provider import ProviderKind
from app.models.user import UserRole
from tests.agent_admin_helpers import fetch_model, make_entry, make_model, make_provider
from tests.conftest import csrf_from_client
from tests.helpers import authed_client

CHAT_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
SECRET = "sk-secreto-del-proveedor-9876"


def _headers(client) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_from_client(client)}


def _tool_call_reply() -> dict:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "modelo-a",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "sofee_ping", "arguments": '{"text": "ok"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    }


def _text_reply() -> dict:
    reply = _tool_call_reply()
    reply["choices"][0]["message"] = {"role": "assistant", "content": "ok"}
    reply["choices"][0]["finish_reason"] = "stop"
    return reply


async def _audit(action: str) -> list[AuditLog]:
    async with async_session_factory() as db:
        return list((await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars())


async def _catalog_with_model(*, supports_tools=None, enabled=True):
    provider = await make_provider("DeepInfra", api_key=SECRET)
    model = await make_model(provider, "modelo-a", supports_tools=supports_tools, enabled=enabled)
    entry = await make_entry("rapido", [model])
    return provider, model, entry


# --- capacidades ---------------------------------------------------------------------------


async def test_capabilities_patch_requires_authentication(client):
    provider, model, _entry = await _catalog_with_model()
    url = f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities"
    assert (await client.patch(url, json={"context_window": 8000})).status_code == 401


async def test_capabilities_patch_is_admin_only(client):
    provider, model, _entry = await _catalog_with_model()
    url = f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities"
    await authed_client(client, role=UserRole.regular)
    resp = await client.patch(url, json={"context_window": 8000}, headers=_headers(client))
    assert resp.status_code == 403


async def test_capabilities_patch_requires_csrf(client):
    provider, model, _entry = await _catalog_with_model()
    url = f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities"
    await authed_client(client)
    assert (await client.patch(url, json={"context_window": 8000})).status_code == 403


async def test_capabilities_patch_updates_only_sent_fields(client):
    await authed_client(client)
    provider, model, _entry = await _catalog_with_model(supports_tools=None)
    url = f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities"

    resp = await client.patch(
        url,
        json={"context_window": 131072, "input_price_per_mtok": 0.27, "output_price_per_mtok": 0.85},
        headers=_headers(client),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["context_window"] == 131072
    assert body["input_price_per_mtok"] == 0.27
    assert body["output_price_per_mtok"] == 0.85
    assert body["supports_tools"] is None

    second = await client.patch(url, json={"supports_tools": True}, headers=_headers(client))
    assert second.json()["supports_tools"] is True
    assert second.json()["context_window"] == 131072

    stored = await fetch_model(model.id)
    assert stored.input_price_per_mtok == Decimal("0.2700")

    cleared = await client.patch(url, json={"context_window": None}, headers=_headers(client))
    assert cleared.json()["context_window"] is None
    assert cleared.json()["supports_tools"] is True

    rows = await _audit("provider.model_capabilities_updated")
    assert len(rows) == 3
    assert rows[0].data["changes"] == {"context_window": 131072, "input_price_per_mtok": "0.27", "output_price_per_mtok": "0.85"}


async def test_capabilities_patch_validates_and_checks_ownership(client):
    await authed_client(client)
    provider, model, _entry = await _catalog_with_model()
    other = await make_provider("Otro", api_key="sk-otro")
    url = f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities"

    negative = await client.patch(url, json={"input_price_per_mtok": -1}, headers=_headers(client))
    assert negative.status_code == 422
    zero_window = await client.patch(url, json={"context_window": 0}, headers=_headers(client))
    assert zero_window.status_code == 422

    wrong_provider = await client.patch(
        f"/api/v1/admin/providers/{other.id}/models/{model.id}/capabilities",
        json={"supports_tools": True},
        headers=_headers(client),
    )
    assert wrong_provider.status_code == 404
    assert (await fetch_model(model.id)).supports_tools is None


async def test_catalog_listing_exposes_agent_readiness_and_binding_capabilities(client):
    await authed_client(client)
    provider, model, entry = await _catalog_with_model(supports_tools=None)

    before = (await client.get("/api/v1/admin/catalog")).json()[0]
    assert before["agent_ready"] is False
    assert before["is_available"] is True
    assert before["bindings"][0]["supports_tools"] is None

    await client.patch(
        f"/api/v1/admin/providers/{provider.id}/models/{model.id}/capabilities",
        json={"supports_tools": True, "context_window": 64000, "input_price_per_mtok": 1.5, "output_price_per_mtok": 6},
        headers=_headers(client),
    )

    after = (await client.get(f"/api/v1/admin/catalog/{entry.id}")).json()
    assert after["agent_ready"] is True
    assert after["context_window"] == 64000
    binding = after["bindings"][0]
    assert binding["supports_tools"] is True
    assert binding["context_window"] == 64000
    assert binding["input_price_per_mtok"] == 1.5
    assert binding["output_price_per_mtok"] == 6.0


async def test_agent_ready_requires_every_available_binding_to_support_tools(client):
    await authed_client(client)
    provider = await make_provider("DeepInfra", api_key=SECRET)
    good = await make_model(provider, "bueno", supports_tools=True)
    untested = await make_model(provider, "sin-probar", supports_tools=None)
    entry = await make_entry("mezcla", [good, untested])

    body = (await client.get(f"/api/v1/admin/catalog/{entry.id}")).json()
    assert body["agent_ready"] is False
    assert body["is_available"] is True


# --- Probar como agente -------------------------------------------------------------------


async def test_agent_test_requires_admin_and_csrf(client):
    _provider, _model, entry = await _catalog_with_model()
    url = f"/api/v1/admin/catalog/{entry.id}/agent-test"

    assert (await client.post(url)).status_code == 401
    await authed_client(client)
    assert (await client.post(url)).status_code == 403


async def test_agent_test_unknown_entry_is_404(client):
    await authed_client(client)
    resp = await client.post(f"/api/v1/admin/catalog/{uuid.uuid4()}/agent-test", headers=_headers(client))
    assert resp.status_code == 404


async def test_agent_test_marks_a_model_that_calls_the_tool(client):
    admin = await authed_client(client)
    _provider, model, entry = await _catalog_with_model()

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_tool_call_reply()))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    assert route.called
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_ready"] is True
    assert body["entry"]["agent_ready"] is True
    [result] = body["results"]
    assert result["verdict"] == "supports"
    assert result["supports_tools"] is True
    assert result["model_id"] == "modelo-a"
    assert result["latency_ms"] is not None

    assert (await fetch_model(model.id)).supports_tools is True
    [row] = await _audit("catalog.agent_tested")
    assert row.actor_id == admin.id
    assert row.data["results"] == [{"model_id": "modelo-a", "verdict": "supports", "supports_tools": True}]


async def test_agent_test_sends_the_probe_tool_and_the_key_stays_out_of_the_response(client):
    await authed_client(client)
    _provider, _model, entry = await _catalog_with_model()

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_tool_call_reply()))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    sent = route.calls.last.request
    assert sent.headers["authorization"] == f"Bearer {SECRET}"
    assert b"sofee_ping" in sent.content
    assert SECRET not in resp.text
    [row] = await _audit("catalog.agent_tested")
    assert SECRET not in str(row.data)


async def test_agent_test_no_tool_call_marks_the_model_as_unfit(client):
    await authed_client(client)
    _provider, model, entry = await _catalog_with_model(supports_tools=True)

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_text_reply()))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    [result] = resp.json()["results"]
    assert result["verdict"] == "no_tool_call"
    assert result["supports_tools"] is False
    assert resp.json()["agent_ready"] is False
    assert (await fetch_model(model.id)).supports_tools is False


async def test_agent_test_rejected_request_marks_the_model_as_unfit(client):
    await authed_client(client)
    _provider, model, entry = await _catalog_with_model()

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        mock.post(CHAT_URL).mock(
            return_value=httpx.Response(400, json={"error": {"message": "tools are not supported"}})
        )
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    [result] = resp.json()["results"]
    assert result["verdict"] == "rejected"
    assert result["supports_tools"] is False
    assert (await fetch_model(model.id)).supports_tools is False


async def test_agent_test_server_error_is_inconclusive_and_keeps_the_flag(client):
    await authed_client(client)
    _provider, model, entry = await _catalog_with_model(supports_tools=True)

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        mock.post(CHAT_URL).mock(return_value=httpx.Response(503, json={"error": "overloaded"}))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    [result] = resp.json()["results"]
    assert result["verdict"] == "inconclusive"
    assert "503" in result["message"]
    assert result["supports_tools"] is True
    assert (await fetch_model(model.id)).supports_tools is True


async def test_agent_test_skips_unavailable_bindings_without_calling_them(client):
    await authed_client(client)
    provider = await make_provider("DeepInfra", api_key=SECRET)
    disabled = await make_model(provider, "apagado", enabled=False)
    working = await make_model(provider, "activo")
    entry = await make_entry("mixto", [disabled, working])

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_tool_call_reply()))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    assert route.call_count == 1
    verdicts = {result["model_id"]: result["verdict"] for result in resp.json()["results"]}
    assert verdicts == {"apagado": "skipped", "activo": "supports"}
    assert (await fetch_model(disabled.id)).supports_tools is None


async def test_agent_test_on_a_provider_without_credentials_is_skipped(client):
    await authed_client(client)
    provider = await make_provider("Sin key", api_key=None)
    model = await make_model(provider, "modelo-x")
    entry = await make_entry("sin-key", [model])

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_tool_call_reply()))
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    assert not route.called
    assert resp.json()["results"][0]["verdict"] == "skipped"
    assert resp.json()["agent_ready"] is False


async def test_agent_test_keeps_the_provider_kind_base_url(client):
    await authed_client(client)
    provider = await make_provider("Gateway", kind=ProviderKind.vercel_gateway, api_key=SECRET)
    model = await make_model(provider, "modelo-gw")
    entry = await make_entry("gateway", [model])

    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        route = mock.post("https://ai-gateway.vercel.sh/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_tool_call_reply())
        )
        resp = await client.post(f"/api/v1/admin/catalog/{entry.id}/agent-test", headers=_headers(client))

    assert route.called
    assert resp.json()["results"][0]["verdict"] == "supports"
