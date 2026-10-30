"""Valoraciones, Compactar, Limpiar, arranque del admin y archivos de /notes/ del agente."""

import asyncio

import pytest_asyncio
from sqlalchemy import select

from app.agent.executor import executor
from app.agent.history import SUMMARY_HEADER
from app.agent.models import ResolvedModel
from app.db import async_session_factory
from app.models.app_setting import AppSetting
from app.models.feedback import MessageFeedback
from tests.agent_fakes import ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import login_through_api


@pytest_asyncio.fixture(autouse=True)
async def _drain_runs():
    yield
    tasks = list(executor._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _install(monkeypatch, model) -> None:
    async def resolver(db, slug):  # noqa: ANN001, ARG001
        return ResolvedModel(
            chat_model=model,
            label="Modelo de prueba",
            catalog_slug="prueba",
            provider_model_id=None,  # type: ignore[arg-type]
            context_window=32_000,
            input_price=None,
            output_price=None,
        )

    monkeypatch.setattr(executor, "model_resolver", resolver)


async def _thread(client, mode: str = "learn") -> None:
    resp = await client.post(
        "/api/v1/threads",
        json={"client_id": "thread-abc", "mode": mode},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text


async def _turn(client, monkeypatch, n: int, answer: str) -> str:
    """Un turno completo (usuario + respuesta). Devuelve el run_id."""
    _install(monkeypatch, ScriptedChatModel(script=[ai(answer)]))
    resp = await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={
            "kind": "send",
            "assistant_client_id": f"asst-{n}",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": f"user-{n}", "text": f"pregunta {n}", "attachment_ids": None},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    await executor.wait(run_id)
    return run_id


def _texts(model) -> list[str]:
    """Textos de la entrada del modelo en su primera llamada, sin el mensaje de sistema."""
    return [str(m.content) for m in model.seen[0] if m.type != "system"]


# --- valoraciones ----------------------------------------------------------------------


async def test_feedback_upsert_retract_and_validation(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    await _turn(client, monkeypatch, 1, "Respuesta uno.")
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    url = "/api/v1/threads/thread-abc/messages/asst-1/feedback"

    assert (await client.put(url, json={"value": "good"}, headers=headers)).status_code == 204
    assert (await client.put(url, json={"value": "bad", "reason": "sin_fuentes", "comment": "faltan"}, headers=headers)).status_code == 204

    async with async_session_factory() as db:
        rows = (await db.execute(select(MessageFeedback))).scalars().all()
    assert len(rows) == 1
    assert (rows[0].value, rows[0].reason, rows[0].comment) == ("bad", "sin_fuentes", "faltan")

    assert (await client.put(url, json={"value": None}, headers=headers)).status_code == 204
    async with async_session_factory() as db:
        assert (await db.execute(select(MessageFeedback))).scalars().all() == []

    user_msg = await client.put(
        "/api/v1/threads/thread-abc/messages/user-1/feedback", json={"value": "good"}, headers=headers
    )
    assert user_msg.status_code == 422
    missing = await client.put(
        "/api/v1/threads/thread-abc/messages/nope/feedback", json={"value": "good"}, headers=headers
    )
    assert missing.status_code == 404
    no_csrf = await client.put(url, json={"value": "good"})
    assert no_csrf.status_code == 403


# --- Compactar y Limpiar ----------------------------------------------------------------


async def test_compact_summarises_older_turns_and_the_next_run_sees_the_summary(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    await _turn(client, monkeypatch, 1, "Un servicio es un programa que atiende peticiones.")
    await _turn(client, monkeypatch, 2, "Se despliega con el pipeline.")

    _install(monkeypatch, ScriptedChatModel(script=[ai("Resumen: se habló de servicios y despliegues.")]))
    compact = await client.post(
        "/api/v1/threads/thread-abc/context/compact", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert compact.status_code == 200, compact.text
    through = compact.json()["summary_through_seq"]
    assert isinstance(through, int)

    detail = (await client.get("/api/v1/threads/thread-abc")).json()
    assert detail["summary_through_seq"] == through
    assert detail["context_start_seq"] is None

    later = ScriptedChatModel(script=[ai("Claro.")])
    _install(monkeypatch, later)
    await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={
            "kind": "send",
            "assistant_client_id": "asst-3",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": "user-3", "text": "¿y el rollback?", "attachment_ids": None},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    await executor.wait((await client.get("/api/v1/threads/thread-abc/runs/latest")).json()["run_id"])
    texts = _texts(later)
    assert texts[0].startswith(SUMMARY_HEADER) and "se habló de servicios" in texts[0]
    assert "Un servicio es un programa" not in " ".join(texts)  # lo resumido no se reenvía
    assert texts[-1] == "¿y el rollback?"


async def test_clear_stops_sending_older_turns_but_keeps_them_visible(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    await _turn(client, monkeypatch, 1, "Primera respuesta.")

    clear = await client.post(
        "/api/v1/threads/thread-abc/context/clear", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert clear.status_code == 200
    cut = clear.json()["context_start_seq"]

    thread = (await client.get("/api/v1/threads/thread-abc")).json()
    assert thread["context_start_seq"] == cut
    assert [m["id"] for m in thread["messages"]] == ["user-1", "asst-1"]  # siguen visibles

    later = ScriptedChatModel(script=[ai("Segunda.")])
    _install(monkeypatch, later)
    await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={
            "kind": "send",
            "assistant_client_id": "asst-2",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": "user-2", "text": "nueva", "attachment_ids": None},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    await executor.wait((await client.get("/api/v1/threads/thread-abc/runs/latest")).json()["run_id"])
    assert _texts(later) == ["nueva"]


async def test_a_summary_older_than_a_clear_is_not_sent(client, monkeypatch):
    """Un resumen anterior a Limpiar deja de enviarse: su corte queda fuera del contexto activo."""
    await login_through_api(client)
    await _thread(client)
    await _turn(client, monkeypatch, 1, "Antes.")
    _install(monkeypatch, ScriptedChatModel(script=[ai("Resumen antiguo.")]))
    await client.post("/api/v1/threads/thread-abc/context/compact", headers={"X-CSRF-Token": csrf_from_client(client)})
    await client.post("/api/v1/threads/thread-abc/context/clear", headers={"X-CSRF-Token": csrf_from_client(client)})

    later = ScriptedChatModel(script=[ai("Vale.")])
    _install(monkeypatch, later)
    await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={
            "kind": "send",
            "assistant_client_id": "asst-2",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": "user-2", "text": "hola", "attachment_ids": None},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    await executor.wait((await client.get("/api/v1/threads/thread-abc/runs/latest")).json()["run_id"])
    assert _texts(later) == ["hola"]


async def test_compaction_without_turns_keeps_the_cut_and_failures_are_502(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    empty = await client.post("/api/v1/threads/thread-abc/context/compact", headers=headers)
    assert empty.status_code == 200 and empty.json() == {"summary_through_seq": None}

    await _turn(client, monkeypatch, 1, "Algo.")

    class Broken(ScriptedChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ARG002
            raise RuntimeError("proveedor caído")

    _install(monkeypatch, Broken(script=[]))
    failed = await client.post("/api/v1/threads/thread-abc/context/compact", headers=headers)
    assert failed.status_code == 502 and failed.json() == {"detail": "summary_failed"}


# --- arranque y archivos ---------------------------------------------------------------


async def test_starters_come_from_app_settings_per_mode_and_locale(client):
    await login_through_api(client)
    async with async_session_factory() as db:
        db.add(AppSetting(key="starters", value={"learn": {"es": ["¿Qué es un servicio?", "   ", "¿Cómo se despliega?"]}}))
        await db.commit()

    es = await client.get("/api/v1/starters", params={"mode": "learn", "locale": "es"})
    assert es.status_code == 200
    assert es.json() == [{"text": "¿Qué es un servicio?"}, {"text": "¿Cómo se despliega?"}]
    assert (await client.get("/api/v1/starters", params={"mode": "learn", "locale": "en"})).json() == []
    assert (await client.get("/api/v1/starters", params={"mode": "research", "locale": "es"})).json() == []
    assert (await client.get("/api/v1/starters", params={"mode": "otro", "locale": "es"})).status_code == 422


async def test_notes_written_by_the_agent_are_listed_and_readable(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    _install(
        monkeypatch,
        ScriptedChatModel(
            script=[
                ai("", [("write_file", {"file_path": "/notes/conceptos.md", "content": "# Conceptos\nDefinición."}, "w1")]),
                ai("Anotado."),
            ]
        ),
    )
    resp = await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={
            "kind": "send",
            "assistant_client_id": "asst-1",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": "user-1", "text": "anota", "attachment_ids": None},
        },
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    run_id = resp.json()["run_id"]
    await executor.wait(run_id)

    events = (await client.get(f"/api/v1/runs/{run_id}/events")).text
    assert "event: file.written" in events
    written = [line for line in events.splitlines() if line.startswith("data: ") and '"path": "/notes/conceptos.md"' in line]
    assert written == ['data: {"path": "/notes/conceptos.md", "size": 24}']

    files = (await client.get("/api/v1/threads/thread-abc/files")).json()
    assert [f["path"] for f in files] == ["/notes/conceptos.md"]
    assert files[0]["size"] == len("# Conceptos\nDefinición.".encode("utf-8"))

    content = (await client.get("/api/v1/threads/thread-abc/files/content", params={"path": "/notes/conceptos.md"})).json()
    assert content == {"path": "/notes/conceptos.md", "content": "# Conceptos\nDefinición."}
    for bad in ("/kb/despliegue.md", "/notes/../x.md", "/notes/no-existe.md"):
        resp = await client.get("/api/v1/threads/thread-abc/files/content", params={"path": bad})
        assert resp.status_code == 404, bad


async def test_thread_payloads_expose_the_context_cut_points(client):
    await login_through_api(client)
    await _thread(client)
    body = (await client.get("/api/v1/threads/thread-abc")).json()
    assert body["summary_through_seq"] is None and body["context_start_seq"] is None
    listed = (await client.get("/api/v1/threads")).json()
    assert listed[0]["summary_through_seq"] is None and listed[0]["context_start_seq"] is None
