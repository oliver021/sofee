"""Runs de punta a punta con la base de conocimiento: citas a documentos, adjuntos, notas,
permisos de solo lectura, búsqueda web con Tavily y los presupuestos de búsquedas.

Modelos con guion (sin red). Tavily se mockea con respx.
"""

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy import select

from app.agent.executor import executor
from app.agent.models import ResolvedModel
from app.agent.persistence import get_agent_storage
from app.db import async_session_factory
from app.models.agent import AgentRun, AgentRunEvent
from app.models.thread import Message, Thread
from app.models.user import UserRole
from app.services.tavily import TAVILY_SEARCH_URL
from tests.agent_fakes import ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user, insert_session

GUIA = "# Guía de despliegue\n\nSe despliega con el pipeline del equipo cada martes."
KEY = "tvly-prueba-9999"


# --- helpers ----------------------------------------------------------------------------


def _resolved(model) -> ResolvedModel:
    return ResolvedModel(
        chat_model=model,
        label="Modelo de prueba",
        catalog_slug="prueba",
        provider_model_id=None,  # type: ignore[arg-type]
        context_window=32_000,
        input_price=Decimal("1"),
        output_price=Decimal("2"),
    )


@pytest.fixture
def use_model(monkeypatch):
    def install(model) -> None:
        async def resolver(db, slug):  # noqa: ANN001, ARG001
            return _resolved(model)

        monkeypatch.setattr(executor, "model_resolver", resolver)

    return install


@pytest_asyncio.fixture(autouse=True)
async def _drain_runs():
    yield
    tasks = list(executor._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _thread(client, mode: str = "learn") -> None:
    resp = await client.post(
        "/api/v1/threads",
        json={"client_id": "thread-abc", "mode": mode},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text


async def _thread_uuid() -> str:
    async with async_session_factory() as db:
        return str((await db.execute(select(Thread.id).where(Thread.client_id == "thread-abc"))).scalar_one())


async def _start(client, *, mode: str = "learn", text: str = "¿Cómo se despliega?", attachment_ids=None):
    body = {
        "kind": "send",
        "assistant_client_id": "asst-1",
        "mode": mode,
        "model_slug": None,
        "user_message": {"client_id": "user-1", "text": text, "attachment_ids": attachment_ids},
    }
    return await client.post(
        "/api/v1/threads/thread-abc/runs",
        json=body,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


async def _run(client, use_model, script, **kwargs) -> str:
    use_model(ScriptedChatModel(script=script))
    resp = await _start(client, **kwargs)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    await executor.wait(run_id)
    return run_id


async def _events(run_id: str) -> list[tuple[str, dict[str, Any]]]:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(AgentRunEvent.type, AgentRunEvent.payload)
                .where(AgentRunEvent.run_id == uuid.UUID(run_id))
                .order_by(AgentRunEvent.seq.asc())
            )
        ).all()
    return [(kind, payload) for kind, payload in rows]


def _finished(events, name: str) -> list[dict[str, Any]]:
    return [payload for kind, payload in events if kind == "tool.finished" and payload["name"] == name]


async def _upload_kb(client, filename: str, text: str) -> str:
    resp = await client.post(
        "/api/v1/admin/kb",
        files=[("files", (filename, text.encode(), "text/markdown"))],
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["documents"][0]["id"]


async def _run_status(run_id: str) -> str:
    async with async_session_factory() as db:
        return (await db.get(AgentRun, uuid.UUID(run_id))).status


# --- documentos del equipo ----------------------------------------------------------------


async def test_reading_a_kb_document_produces_a_citation_that_resolves_to_it(client, use_model):
    await authed_client(client)
    doc_id = await _upload_kb(client, "despliegue.md", GUIA)
    await _thread(client)

    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "r1")]),
            ai("Se despliega cada martes [1]."),
        ],
    )
    assert await _run_status(run_id) == "completed"
    events = await _events(run_id)
    source = {"index": 1, "title": "Guía de despliegue", "url": None, "kind": "kb", "ref": doc_id}
    assert [p for kind, p in events if kind == "source.added"] == [source]
    assert _finished(events, "read_file")[0]["result_preview"].startswith("Fuente [1]: Guía de despliegue")

    completed = events[-1][1]
    assert completed["text"] == "Se despliega cada martes [1]."
    assert completed["citations"] == [{**source, "snippet": None}]
    async with async_session_factory() as db:
        message = (await db.execute(select(Message).where(Message.client_id == "asst-1"))).scalar_one()
    assert message.citations == completed["citations"]


async def test_search_team_docs_returns_numbered_results_and_registers_them(client, use_model):
    await authed_client(client)
    doc_id = await _upload_kb(client, "despliegue.md", GUIA)
    await _upload_kb(client, "onboarding.md", "# Onboarding\n\nPrimeros pasos con el correo corporativo.")
    await _thread(client)

    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("search_team_docs", {"query": "pipeline"}, "s1")]),
            ai("El pipeline despliega cada martes [1]."),
        ],
    )
    events = await _events(run_id)
    search = _finished(events, "search_team_docs")[0]
    assert search["status"] == "success"
    assert search["result_preview"].startswith("[1] Guía de despliegue — ")
    assert "pipeline" in search["result_preview"]
    assert [p["ref"] for kind, p in events if kind == "source.added"] == [doc_id]
    assert events[-1][1]["citations"][0]["snippet"].count("pipeline") == 1
    # La herramienta avisa de lo que hace por el stream custom: llega como evento `status`.
    assert {"text": "Buscando en la documentación del equipo"} in [p for kind, p in events if kind == "status"]


async def test_disabled_documents_disappear_from_the_agent(client, use_model):
    await authed_client(client)
    doc_id = await _upload_kb(client, "despliegue.md", GUIA)
    await client.patch(
        f"/api/v1/admin/kb/{doc_id}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    await _thread(client)

    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "r1")]),
            ai("No tengo ese documento."),
        ],
    )
    events = await _events(run_id)
    assert not [p for kind, p in events if kind == "source.added"]
    assert _finished(events, "read_file")[0]["result_preview"].startswith("Error")


async def test_the_agent_cannot_write_into_the_knowledge_base(client, use_model):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", GUIA)
    await _thread(client)

    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("write_file", {"file_path": "/kb/nuevo.md", "content": "intruso"}, "w1")]),
            ai("No puedo escribir ahí."),
        ],
    )
    write = _finished(await _events(run_id), "write_file")[0]
    assert write["status"] == "error"
    assert "permission denied" in write["result_preview"]


# --- adjuntos del hilo --------------------------------------------------------------------


async def test_attachment_text_is_copied_for_the_run_and_cited_by_its_storage_object(client, use_model):
    await authed_client(client)
    resp = await client.post(
        "/api/v1/storage",
        files={"file": ("notas reunion.txt", "La reunión es el martes a las 10.".encode(), "text/plain")},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    attachment_id = resp.json()["id"]
    await _thread(client)

    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("read_file", {"file_path": "/attachments/notas_reunion.txt"}, "a1")]),
            ai("La reunión es el martes [1]."),
        ],
        attachment_ids=[attachment_id],
    )
    thread_id = await _thread_uuid()
    item = await get_agent_storage().store.aget((thread_id, "attachments"), "/notas_reunion.txt")
    assert item is not None and item.value["content"] == "La reunión es el martes a las 10."

    events = await _events(run_id)
    assert [p for kind, p in events if kind == "source.added"] == [
        {"index": 1, "title": "notas reunion.txt", "url": None, "kind": "attachment", "ref": attachment_id}
    ]


async def test_attachments_of_other_users_are_not_copied(client, use_model):
    await authed_client(client)
    resp = await client.post(
        "/api/v1/storage",
        files={"file": ("ajeno.txt", b"secreto ajeno", "text/plain")},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    foreign_id = resp.json()["id"]

    other = await create_user(email="otro@example.com", role=UserRole.regular)
    session = await insert_session(other.id)
    client.cookies.set("sofee_session", str(session.id))
    await _thread(client)
    run_id = await _run(
        client,
        use_model,
        [ai("No tengo acceso a ese archivo.")],
        attachment_ids=[foreign_id],
    )
    assert await _run_status(run_id) == "completed"
    thread_id = await _thread_uuid()
    assert await get_agent_storage().store.aget((thread_id, "attachments"), "/ajeno.txt") is None


# --- notas del agente ---------------------------------------------------------------------


async def test_notes_written_by_the_agent_are_listed_read_and_announced(client, use_model):
    await authed_client(client)
    await _thread(client)
    run_id = await _run(
        client,
        use_model,
        [
            ai("", [("write_file", {"file_path": "/notes/resumen.md", "content": "# Resumen\n\nPuntos clave."}, "w1")]),
            ai("Dejé el resumen en /notes/resumen.md."),
        ],
    )
    written = [p for kind, p in await _events(run_id) if kind == "file.written"]
    assert written == [{"path": "/notes/resumen.md", "size": len("# Resumen\n\nPuntos clave.".encode())}]

    listed = (await client.get("/api/v1/threads/thread-abc/files")).json()
    assert [item["path"] for item in listed] == ["/notes/resumen.md"]
    content = (await client.get("/api/v1/threads/thread-abc/files/content", params={"path": "/notes/resumen.md"})).json()
    assert content == {"path": "/notes/resumen.md", "content": "# Resumen\n\nPuntos clave."}
    assert (await client.get("/api/v1/threads/thread-abc/files/content", params={"path": "/kb/x.md"})).status_code == 404
    assert (await client.get("/api/v1/threads/thread-abc/files/content", params={"path": "/notes/../kb/x.md"})).status_code == 404


async def test_other_users_cannot_list_or_read_notes(client, use_model):
    await authed_client(client)
    await _thread(client)
    await _run(client, use_model, [ai("", [("write_file", {"file_path": "/notes/privado.md", "content": "x"}, "w1")]), ai("Hecho.")])

    other = await create_user(email="curioso@example.com", role=UserRole.regular)
    session = await insert_session(other.id)
    client.cookies.set("sofee_session", str(session.id))
    assert (await client.get("/api/v1/threads/thread-abc/files")).status_code == 404
    assert (await client.get("/api/v1/threads/thread-abc/files/content", params={"path": "/notes/privado.md"})).status_code == 404


# --- búsqueda web y presupuestos ----------------------------------------------------------


async def _set_key(client) -> None:
    resp = await client.put(
        "/api/v1/admin/integrations/tavily",
        json={"api_key": KEY},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200, resp.text


async def test_web_search_with_a_tavily_key_is_numbered_and_cited_as_web(client, use_model):
    await authed_client(client)
    await _set_key(client)
    await _thread(client, mode="explore")
    tavily = {
        "results": [
            {"title": "FastAPI", "url": "https://fastapi.tiangolo.com/", "content": "Framework web de Python."}
        ]
    }
    with respx.mock(assert_all_mocked=True) as mock:
        route = mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(200, json=tavily))
        run_id = await _run(
            client,
            use_model,
            [ai("", [("web_search", {"query": "fastapi"}, "w1")]), ai("Es un framework web [1].")],
            mode="explore",
        )
    assert route.call_count == 1
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"

    events = await _events(run_id)
    search = _finished(events, "web_search")[0]
    assert search["status"] == "success"
    assert search["result_preview"].startswith("[1] FastAPI — fastapi.tiangolo.com")
    assert {"text": "Buscando en la web"} in [p for kind, p in events if kind == "status"]
    assert events[-1][1]["citations"] == [
        {
            "index": 1,
            "title": "FastAPI",
            "url": "https://fastapi.tiangolo.com/",
            "kind": "web",
            "snippet": "Framework web de Python.",
            "ref": None,
        }
    ]


async def test_a_failing_tavily_call_is_a_tool_error_and_the_run_still_completes(client, use_model):
    await authed_client(client)
    await _set_key(client)
    await _thread(client, mode="explore")
    with respx.mock(assert_all_mocked=True) as mock:
        mock.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(500))
        run_id = await _run(
            client,
            use_model,
            [ai("", [("web_search", {"query": "fastapi"}, "w1")]), ai("No pude buscar en la web.")],
            mode="explore",
        )
    assert await _run_status(run_id) == "completed"
    search = _finished(await _events(run_id), "web_search")[0]
    assert search["status"] == "error"
    assert "código 500" in search["result_preview"]


async def test_the_search_budget_of_the_profile_is_enforced_by_the_tools(client, use_model):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", GUIA)
    await _thread(client, mode="explore")
    # El perfil de explore permite 3 búsquedas por run.
    script = [ai("", [("search_team_docs", {"query": "pipeline"}, f"s{i}")]) for i in range(4)]
    script.append(ai("Esto es lo que encontré [1]."))
    run_id = await _run(client, use_model, script, mode="explore")

    searches = _finished(await _events(run_id), "search_team_docs")
    assert [s["status"] for s in searches] == ["success", "success", "success", "error"]
    assert searches[3]["result_preview"].startswith("Error: se alcanzó el límite de 3 búsquedas")


async def test_a_run_without_tavily_key_never_offers_web_search(client, use_model, monkeypatch):
    from app.agent import executor as executor_module

    seen: dict[str, Any] = {}
    original = executor_module.get_tools

    def spy(mode, config, **kwargs):  # noqa: ANN001, ANN003, ANN202
        seen.update(kwargs)
        return original(mode, config, **kwargs)

    monkeypatch.setattr(executor_module, "get_tools", spy)
    await authed_client(client)
    await _thread(client, mode="explore")
    await _run(client, use_model, [ai("Respondo sin buscar.")], mode="explore")
    assert seen == {"web_search": False}
