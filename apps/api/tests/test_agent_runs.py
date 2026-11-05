"""Runs de punta a punta: executor, persistencia de eventos, SSE, cancelación y revisión del plan.

Modelos falsos con guion (sin red). El SSE se prueba por el generador y por el ASGI crudo,
porque httpx.ASGITransport espera a que la aplicación termine antes de devolver el cuerpo.
"""

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.agent.executor import executor
from app.agent.models import ModelUnavailable, ResolvedModel
from app.agent.persistence import get_agent_storage
from app.db import async_session_factory
from app.models.agent import AgentProfile, AgentRun, AgentRunEvent
from app.models.app_setting import AppSetting
from app.models.audit import AuditLog
from app.models.thread import Message, Thread
from tests.agent_fakes import GatedChatModel, ProviderOutageChatModel, ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import login_through_api

DESPLIEGUE_DOC = "# Despliegue\n\nSe despliega con el pipeline del equipo."
TERMINAL = {"run.completed", "run.failed", "run.cancelled"}


# --- helpers ----------------------------------------------------------------------------


def _resolved(model) -> ResolvedModel:
    # provider_model_id es None: el run no toca provider_models en los tests.
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
    """Instala un modelo falso como resolvedor de catálogo para el run."""

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


async def _thread(client, client_id: str = "thread-abc", mode: str = "learn") -> None:
    resp = await client.post(
        "/api/v1/threads",
        json={"client_id": client_id, "mode": mode},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text


async def _start(
    client,
    *,
    kind: str = "send",
    mode: str = "learn",
    text: str = "¿Qué es un servicio?",
    user_id: str = "user-1",
    assistant_id: str = "asst-1",
    thread: str = "thread-abc",
):
    body: dict[str, Any] = {"kind": kind, "assistant_client_id": assistant_id, "mode": mode, "model_slug": None}
    if kind == "send":
        body["user_message"] = {"client_id": user_id, "text": text, "attachment_ids": None}
    return await client.post(
        f"/api/v1/threads/{thread}/runs",
        json=body,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


async def _run_row(run_id: str) -> AgentRun:
    async with async_session_factory() as db:
        return await db.get(AgentRun, uuid.UUID(run_id))


async def _message_row(client_id: str, thread_client_id: str = "thread-abc") -> Message:
    async with async_session_factory() as db:
        return (
            await db.execute(
                select(Message)
                .join(Thread, Thread.id == Message.thread_id)
                .where(Message.client_id == client_id, Thread.client_id == thread_client_id)
            )
        ).scalar_one()


async def _events(run_id: str) -> list[tuple[int, str, dict[str, Any]]]:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(AgentRunEvent.seq, AgentRunEvent.type, AgentRunEvent.payload)
                .where(AgentRunEvent.run_id == uuid.UUID(run_id))
                .order_by(AgentRunEvent.seq.asc())
            )
        ).all()
    return [(seq, kind, payload) for seq, kind, payload in rows]


def _types(events) -> list[str]:
    return [kind for _, kind, _ in events]


def _is_subsequence(expected: list[str], actual: list[str]) -> bool:
    it = iter(actual)
    return all(any(item == got for got in it) for item in expected)


def _parse_sse(text: str) -> list[dict[str, str]]:
    frames = []
    for block in text.split("\n\n"):
        frame: dict[str, str] = {}
        for line in block.split("\n"):
            if line.startswith(":") or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            frame[key] = value
        if frame:
            frames.append(frame)
    return frames


def _seed_kb(path: str = "/despliegue.md", content: str = DESPLIEGUE_DOC) -> None:
    get_agent_storage().store.put(
        ("kb",),
        path,
        {"content": content, "encoding": "utf-8", "created_at": "2026-01-01T00:00:00+00:00", "modified_at": "2026-01-01T00:00:00+00:00"},
    )


RESEARCH_PLAN = {"todos": [{"content": "buscar", "status": "in_progress"}]}


def _research_script() -> list:
    """Plan (revisión), delegación en `investigador`, lectura de la KB, resumen y respuesta con [1]."""
    return [
        ai("Plan. ", [("write_todos", RESEARCH_PLAN, "t1")]),
        ai("", [("task", {"description": "investiga el despliegue", "subagent_type": "investigador"}, "k1")]),
        ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "s1")]),
        ai("Resumen del despliegue [1]."),
        ai("Se despliega con el pipeline del equipo [1]."),
    ]


# --- ejecución de punta a punta ---------------------------------------------------------


async def test_learn_run_persists_events_message_and_serves_sse(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(
        ScriptedChatModel(
            script=[
                ai("", [("write_todos", {"todos": [{"content": "definir", "status": "in_progress"}]}, "t1")]),
                ai("Una definición corta."),
            ]
        )
    )

    resp = await _start(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["assistant_message_id"] == "asst-1"
    run_id = body["run_id"]

    await executor.wait(run_id)
    run = await _run_row(run_id)
    assert run.status == "completed"
    assert run.input_tokens == 20 and run.output_tokens == 10  # dos llamadas de 10 y 5
    assert run.ttft_ms is not None and run.cost_estimate == Decimal("0.000040")

    message = await _message_row("asst-1")
    assert message.role == "assistant" and message.status == "complete"
    assert message.text == "Una definición corta."

    events = await _events(run_id)
    assert [seq for seq, _, _ in events] == list(range(1, len(events) + 1))
    types = _types(events)
    assert types[0] == "run.started" and types[-1] == "run.completed"
    assert events[0][2] == {
        "run_id": run_id,
        "assistant_message_id": "asst-1",
        "mode": "learn",
        "model_label": "Modelo de prueba",
    }
    deltas = "".join(payload["text"] for _, kind, payload in events if kind == "message.delta")
    assert deltas.strip() == "Una definición corta."
    assert _is_subsequence(["tool.started", "tool.finished", "todos.updated"], types)
    assert events[-1][2]["text"] == "Una definición corta."

    # SSE completo: el cuerpo coincide con lo persistido, sin huecos ni duplicados.
    stream = await client.get(f"/api/v1/runs/{run_id}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.headers["x-accel-buffering"] == "no"
    frames = _parse_sse(stream.text)
    assert [int(f["id"]) for f in frames] == [seq for seq, _, _ in events]
    assert [f["event"] for f in frames] == types


async def test_sse_last_event_id_resumes_without_gaps_or_duplicates(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("Hola a todos.")]))
    run_id = (await _start(client)).json()["run_id"]
    await executor.wait(run_id)
    expected = await _events(run_id)
    assert len(expected) >= 4

    resumed = await client.get(f"/api/v1/runs/{run_id}/events", headers={"Last-Event-ID": "3"})
    seqs = [int(f["id"]) for f in _parse_sse(resumed.text)]
    assert seqs == [seq for seq, _, _ in expected if seq > 3]

    by_query = await client.get(f"/api/v1/runs/{run_id}/events?after={expected[-2][0]}")
    assert [int(f["id"]) for f in _parse_sse(by_query.text)] == [expected[-1][0]]


async def test_cancel_midrun_keeps_partial_text_and_stops_the_message(client, use_model):
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    model = GatedChatModel(script=[ai("Hola gente que sigue leyendo esto")], gate=gate)
    use_model(model)
    run_id = (await _start(client)).json()["run_id"]

    # Espera a que llegue el primer token persistido, sin depender de tiempos.
    for _ in range(200):
        if any(kind == "message.delta" for _, kind, _ in await _events(run_id)):
            break
        await asyncio.sleep(0.01)
    assert (await _run_row(run_id)).status == "running"

    cancelled = await client.post(
        f"/api/v1/runs/{run_id}/cancel", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert cancelled.status_code == 202
    await executor.wait(run_id)

    run = await _run_row(run_id)
    assert run.status == "cancelled" and run.finished_at is not None
    message = await _message_row("asst-1")
    assert message.status == "stopped"
    assert message.text == "Hola "  # solo lo que llegó antes de cancelar
    events = await _events(run_id)
    assert _types(events)[-1] == "run.cancelled"
    assert events[-1][2]["text"] == message.text

    async with async_session_factory() as db:
        audit = (
            await db.execute(select(AuditLog).where(AuditLog.action == "agent.run_cancelled"))
        ).scalars().all()
    assert len(audit) == 1 and audit[0].resource_id == run_id


async def test_cancel_of_a_paused_run_settles_without_a_task(client, use_model):
    await login_through_api(client)
    await _thread(client, mode="research")
    use_model(ScriptedChatModel(script=_research_script()))
    run_id = (await _start(client, mode="research")).json()["run_id"]
    await executor.wait(run_id)
    assert (await _run_row(run_id)).status == "interrupted"

    resp = await client.post(
        f"/api/v1/runs/{run_id}/cancel", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 202
    assert (await _run_row(run_id)).status == "cancelled"
    assert (await _message_row("asst-1")).status == "stopped"
    assert _types(await _events(run_id))[-1] == "run.cancelled"


async def test_research_plan_review_then_approve_cites_the_knowledge_base(client, use_model):
    await login_through_api(client)
    await _thread(client, mode="research")
    _seed_kb()
    use_model(ScriptedChatModel(script=_research_script()))
    run_id = (await _start(client, mode="research", text="¿Migramos?")).json()["run_id"]

    await executor.wait(run_id)
    assert (await _run_row(run_id)).status == "interrupted"
    paused = await _events(run_id)
    interrupt = [payload for _, kind, payload in paused if kind == "interrupt"]
    assert interrupt == [
        {"interrupt_id": interrupt[0]["interrupt_id"], "kind": "plan_review", "todos": [{"content": "buscar", "status": "in_progress"}]}
    ]
    assert _types(paused)[-1] == "interrupt"  # todavía no hay evento terminal

    resumed = await client.post(
        f"/api/v1/runs/{run_id}/resume",
        json={"decision": "approve"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resumed.status_code == 202
    await executor.wait(run_id)

    run = await _run_row(run_id)
    assert run.status == "completed"
    events = await _events(run_id)
    assert _is_subsequence(
        [
            "run.started",
            "interrupt",
            "tool.finished",  # write_todos tras aprobar
            "subagent.started",
            "source.added",
            "subagent.finished",
            "run.completed",
        ],
        _types(events),
    )
    sources = [payload for _, kind, payload in events if kind == "source.added"]
    assert sources == [{"index": 1, "title": "despliegue", "url": None, "kind": "kb", "ref": "/kb/despliegue.md"}]

    # El texto final es lo que el usuario vio en streaming: incluye el "Plan." previo a la herramienta.
    completed = events[-1][2]
    assert completed["text"] == "Plan. Se despliega con el pipeline del equipo [1]."
    assert completed["citations"] == [
        {"index": 1, "title": "despliegue", "url": None, "kind": "kb", "snippet": None, "ref": "/kb/despliegue.md"}
    ]
    message = await _message_row("asst-1")
    assert message.status == "complete"
    assert message.citations == completed["citations"]


async def test_resume_with_edit_replaces_the_plan(client, use_model):
    await login_through_api(client)
    await _thread(client, mode="research")
    use_model(
        ScriptedChatModel(
            script=[
                ai("", [("write_todos", {"todos": [{"content": "original", "status": "pending"}]}, "t1")]),
                ai("Informe con el plan editado."),
            ]
        )
    )
    run_id = (await _start(client, mode="research")).json()["run_id"]
    await executor.wait(run_id)

    edited = [{"content": "plan editado", "status": "pending"}]
    resp = await client.post(
        f"/api/v1/runs/{run_id}/resume",
        json={"decision": "edit", "todos": edited},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 202
    await executor.wait(run_id)

    todos = [payload["items"] for _, kind, payload in await _events(run_id) if kind == "todos.updated"]
    assert todos == [edited]
    assert (await _run_row(run_id)).status == "completed"
    assert (await _message_row("asst-1")).text == "Informe con el plan editado."


async def test_resume_rejects_runs_that_are_not_paused_and_bad_edits(client, use_model):
    await login_through_api(client)
    await _thread(client, mode="research")
    use_model(ScriptedChatModel(script=[ai("Listo.")]))
    run_id = (await _start(client, mode="research")).json()["run_id"]
    await executor.wait(run_id)
    headers = {"X-CSRF-Token": csrf_from_client(client)}

    not_paused = await client.post(f"/api/v1/runs/{run_id}/resume", json={"decision": "approve"}, headers=headers)
    assert not_paused.status_code == 409 and not_paused.json()["detail"] == "not_interrupted"

    no_todos = await client.post(f"/api/v1/runs/{run_id}/resume", json={"decision": "edit"}, headers=headers)
    assert no_todos.status_code == 422


# --- concurrencia, validación y errores ------------------------------------------------


async def test_second_run_on_a_busy_thread_is_rejected(client, use_model):
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("uno dos tres"), ai("ok")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]

    busy = await _start(client, user_id="user-2", assistant_id="asst-2")
    assert busy.status_code == 409 and busy.json() == {"detail": "run_active"}

    gate.set()
    await executor.wait(run_id)
    free = await _start(client, user_id="user-3", assistant_id="asst-3")
    assert free.status_code == 201


async def test_runs_require_csrf_and_a_send_needs_the_user_message(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("x")]))
    body = {"kind": "send", "assistant_client_id": "a", "mode": "learn", "model_slug": None,
            "user_message": {"client_id": "u", "text": "hola", "attachment_ids": None}}
    no_csrf = await client.post("/api/v1/threads/thread-abc/runs", json=body)
    assert no_csrf.status_code == 403

    missing = await client.post(
        "/api/v1/threads/thread-abc/runs",
        json={"kind": "send", "assistant_client_id": "a", "mode": "learn"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert missing.status_code == 422


async def test_agent_disabled_answers_503_and_creates_nothing(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("x")]))
    async with async_session_factory() as db:
        db.add(AppSetting(key="agent.enabled", value=False))
        await db.commit()

    resp = await _start(client)
    assert resp.status_code == 503 and resp.json() == {"detail": "agent_disabled"}
    async with async_session_factory() as db:
        assert (await db.execute(select(func.count(AgentRun.id)))).scalar_one() == 0


async def test_quota_exceeded_answers_429_with_reset_time(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("uno"), ai("dos")]))
    async with async_session_factory() as db:
        db.add(AppSetting(key="quotas", value={"regular": {"runs_per_day": 1}}))
        await db.commit()

    first = await _start(client)
    await executor.wait(first.json()["run_id"])
    second = await _start(client, user_id="user-2", assistant_id="asst-2")
    assert second.status_code == 429
    body = second.json()
    assert body["detail"] == "quota_exceeded" and body["reset_at"].endswith("+00:00")


async def test_model_unavailable_becomes_a_run_failure(client, monkeypatch):
    await login_through_api(client)
    await _thread(client)

    async def unavailable(db, slug):  # noqa: ANN001, ARG001
        raise ModelUnavailable("sin bindings")

    monkeypatch.setattr(executor, "model_resolver", unavailable)
    run_id = (await _start(client)).json()["run_id"]
    await executor.wait(run_id)

    events = await _events(run_id)
    assert _types(events) == ["run.failed"]
    assert events[0][2] == {"error_code": "model_unavailable", "message": "No usable model binding for the agent", "retryable": False}
    assert (await _run_row(run_id)).status == "failed"
    assert (await _message_row("asst-1")).status == "error"


async def test_provider_outage_maps_to_provider_error(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ProviderOutageChatModel())
    run_id = (await _start(client)).json()["run_id"]
    await executor.wait(run_id)

    events = await _events(run_id)
    assert _types(events)[-1] == "run.failed"
    assert events[-1][2]["error_code"] == "provider_error"
    assert events[-1][2]["retryable"] is True
    run = await _run_row(run_id)
    assert run.status == "failed" and run.error_code == "provider_error"


async def test_run_past_its_time_limit_fails_with_timeout(client, use_model):
    await login_through_api(client)
    await _thread(client)
    async with async_session_factory() as db:
        db.add(AgentProfile(mode="learn", version=1, is_active=True, system_prompt="p", config={"limits": {"max_seconds": 0.2}}))
        await db.commit()
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("se queda esperando")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]
    await executor.wait(run_id)

    events = await _events(run_id)
    assert events[-1][1] == "run.failed"
    assert events[-1][2]["error_code"] == "timeout" and events[-1][2]["retryable"] is True


async def test_other_users_cannot_see_or_touch_a_run(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("hola")]))
    run_id = (await _start(client)).json()["run_id"]
    await executor.wait(run_id)

    await login_through_api(client, email="other@example.com")
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    assert (await client.get(f"/api/v1/runs/{run_id}/events")).status_code == 404
    assert (await client.post(f"/api/v1/runs/{run_id}/cancel", headers=headers)).status_code == 404
    assert (await client.post(f"/api/v1/runs/{run_id}/resume", json={"decision": "approve"}, headers=headers)).status_code == 404
    assert (await client.get("/api/v1/threads/thread-abc/runs")).status_code == 404
    assert (await client.get("/api/v1/threads/thread-abc/runs/latest")).status_code == 404
    assert (await client.get("/api/v1/runs/not-a-uuid/events")).status_code == 404


async def test_server_owns_assistant_messages_of_runs(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("respuesta")]))
    await _start(client)
    await executor.wait((await _latest(client))["run_id"])

    headers = {"X-CSRF-Token": csrf_from_client(client)}
    body = {"client_id": "asst-1", "role": "assistant", "text": "pirata", "status": "complete"}
    blocked = await client.post("/api/v1/threads/thread-abc/messages", json=body, headers=headers)
    assert blocked.status_code == 409 and blocked.json() == {"detail": "server_owned"}

    # Un mensaje de modo mock, sin run, sigue siendo escribible por el cliente.
    mock = await client.post(
        "/api/v1/threads/thread-abc/messages",
        json={**body, "client_id": "mock-1"},
        headers=headers,
    )
    assert mock.status_code == 201


async def _latest(client) -> dict[str, Any]:
    resp = await client.get("/api/v1/threads/thread-abc/runs/latest")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_list_runs_and_latest_hide_deltas_and_204_without_runs(client, use_model):
    await login_through_api(client)
    await _thread(client)
    assert (await client.get("/api/v1/threads/thread-abc/runs/latest")).status_code == 204

    use_model(ScriptedChatModel(script=[ai("Primera respuesta.")]))
    first = (await _start(client)).json()["run_id"]
    await executor.wait(first)
    use_model(ScriptedChatModel(script=[ai("Segunda respuesta.")]))
    second = (await _start(client, text="otra", user_id="user-2", assistant_id="asst-2")).json()["run_id"]
    await executor.wait(second)

    runs = (await client.get("/api/v1/threads/thread-abc/runs")).json()
    assert [r["run_id"] for r in runs] == [first, second]
    assert runs[0]["assistant_message_id"] == "asst-1" and runs[0]["status"] == "completed"
    assert all(kind != "message.delta" for r in runs for kind in (e["type"] for e in r["events"]))
    assert runs[0]["events"][0]["type"] == "run.started"

    latest = await _latest(client)
    assert latest["run_id"] == second and "events" not in latest


async def test_regenerate_and_continue_reuse_the_assistant_message(client, use_model):
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("Hola gente y mucho más")], gate=gate))
    first = (await _start(client)).json()["run_id"]
    for _ in range(200):
        if any(kind == "message.delta" for _, kind, _ in await _events(first)):
            break
        await asyncio.sleep(0.01)
    await client.post(f"/api/v1/runs/{first}/cancel", headers={"X-CSRF-Token": csrf_from_client(client)})
    await executor.wait(first)
    partial = (await _message_row("asst-1")).text
    assert partial and partial.startswith("Hola")

    # Se continúa el texto parado: el modelo recibe la parte ya escrita y la instrucción de seguir.
    cont_model = ScriptedChatModel(script=[ai("y bienvenidos.")])
    use_model(cont_model)
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    body = {"kind": "continue", "assistant_client_id": "asst-1", "mode": "learn", "model_slug": None}
    resumed = await client.post("/api/v1/threads/thread-abc/runs", json=body, headers=headers)
    assert resumed.status_code == 201, resumed.text
    await executor.wait(resumed.json()["run_id"])
    message = await _message_row("asst-1")
    assert message.status == "complete"
    assert message.text.startswith(partial.strip()) and message.text.endswith("y bienvenidos.")
    assert any(m.type == "ai" and m.content == partial for m in cont_model.seen[0])
    assert cont_model.seen[0][-1].type == "human"

    # Regenerar reemplaza el texto: el historial solo lleva el mensaje del usuario, sin la respuesta vieja.
    regen_model = ScriptedChatModel(script=[ai("Otra versión.")])
    use_model(regen_model)
    body = {"kind": "regenerate", "assistant_client_id": "asst-1", "mode": "learn", "model_slug": None}
    regen = await client.post("/api/v1/threads/thread-abc/runs", json=body, headers=headers)
    assert regen.status_code == 201
    await executor.wait(regen.json()["run_id"])
    assert (await _message_row("asst-1")).text == "Otra versión."
    assert [m.type for m in regen_model.seen[0] if m.type != "system"] == ["human"]


async def test_continue_needs_a_stopped_message(client, use_model):
    await login_through_api(client)
    await _thread(client)
    use_model(ScriptedChatModel(script=[ai("terminado")]))
    await _start(client)
    await executor.wait((await _latest(client))["run_id"])
    body = {"kind": "continue", "assistant_client_id": "asst-1", "mode": "learn", "model_slug": None}
    resp = await client.post(
        "/api/v1/threads/thread-abc/runs", json=body, headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 409 and resp.json() == {"detail": "not_stopped"}


# --- streaming ---------------------------------------------------------------------------


async def test_stream_yields_heartbeats_while_the_run_is_idle(client, use_model):
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("una dos")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]
    for _ in range(200):
        if any(kind == "message.delta" for _, kind, _ in await _events(run_id)):
            break
        await asyncio.sleep(0.01)

    stream = executor.stream(run_id, 0, heartbeat=0.01)
    items = []
    async for item in stream:
        items.append(item)
        if len(items) >= 4:
            break
    await stream.aclose()
    assert items[0] is not None and items[0].type == "run.started"
    assert any(item is None for item in items[1:])  # latidos mientras el modelo espera
    gate.set()
    await executor.wait(run_id)


async def test_first_event_arrives_through_the_real_middleware_before_the_run_ends(client, use_model):
    """El SSE atraviesa SecurityHeadersMiddleware sin esperar al final del run."""
    from app.main import app

    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("primero segundo")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]

    sent: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        await sent.put(message)

    cookie = client.cookies.get("sofee_session")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/v1/runs/{run_id}/events",
        "raw_path": f"/api/v1/runs/{run_id}/events".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test"), (b"cookie", f"sofee_session={cookie}".encode())],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    app_task = asyncio.create_task(app(scope, receive, send))
    try:
        body = b""
        while b"event: run.started" not in body:
            message = await asyncio.wait_for(sent.get(), timeout=5)
            if message["type"] == "http.response.body":
                body += message.get("body", b"")
        # El primer evento ya llegó y el run sigue vivo: el stream no esperó al final.
        assert (await _run_row(run_id)).status == "running"
        assert not app_task.done()

        gate.set()
        await executor.wait(run_id)
        body += await _drain(sent, app_task)
        assert b"event: run.completed" in body
    finally:
        disconnect.set()
        await asyncio.wait_for(app_task, timeout=5)


async def _drain(sent: asyncio.Queue, app_task: asyncio.Task) -> bytes:
    """Lee lo que quede del cuerpo hasta que la aplicación termine."""
    data = b""
    while True:
        try:
            message = await asyncio.wait_for(sent.get(), timeout=0.5)
        except TimeoutError:
            if app_task.done():
                return data
            continue
        if message["type"] == "http.response.body":
            data += message.get("body", b"")


async def test_client_disconnect_releases_the_subscription(client, use_model, monkeypatch):
    """Una desconexión a mitad de run libera la suscripción aunque el run siga vivo."""
    from app.api.routes import runs as runs_routes
    from app.main import app

    monkeypatch.setattr(runs_routes, "HEARTBEAT_SECONDS", 0.05)
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("hola mundo")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]

    sent: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        await sent.put(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/v1/runs/{run_id}/events",
        "raw_path": f"/api/v1/runs/{run_id}/events".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test"), (b"cookie", f"sofee_session={client.cookies.get('sofee_session')}".encode())],
        "client": ("127.0.0.1", 50001),
        "server": ("test", 80),
    }
    app_task = asyncio.create_task(app(scope, receive, send))
    try:
        body = b""
        while b"event: run.started" not in body:
            message = await asyncio.wait_for(sent.get(), timeout=5)
            if message["type"] == "http.response.body":
                body += message.get("body", b"")
        assert run_id in executor._subscribers

        disconnect.set()
        await asyncio.wait_for(app_task, timeout=5)
        assert run_id not in executor._subscribers
        assert (await _run_row(run_id)).status == "running"
    finally:
        gate.set()
        await executor.wait(run_id)


async def test_open_stream_does_not_hold_a_db_connection(client, use_model):
    """Un SSE abierto no deja su sesión de la petición idle in transaction."""
    from app.main import app

    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("hola mundo")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]

    sent: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()

    async def receive():
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        await sent.put(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/v1/runs/{run_id}/events",
        "raw_path": f"/api/v1/runs/{run_id}/events".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test"), (b"cookie", f"sofee_session={client.cookies.get('sofee_session')}".encode())],
        "client": ("127.0.0.1", 50002),
        "server": ("test", 80),
    }
    app_task = asyncio.create_task(app(scope, receive, send))
    try:
        body = b""
        while b"event: run.started" not in body:
            message = await asyncio.wait_for(sent.get(), timeout=5)
            if message["type"] == "http.response.body":
                body += message.get("body", b"")
        # El ejecutor abre transacciones de milisegundos al guardar cada evento, y una consulta
        # puede caer justo en una. Lo que importa es que ninguna se quede abierta mientras el
        # SSE sigue conectado: se reintenta durante un segundo.
        idle = 1
        for _ in range(10):
            async with async_session_factory() as db:
                idle = (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND state = 'idle in transaction'"
                        )
                    )
                ).scalar_one()
            if idle == 0:
                break
            await asyncio.sleep(0.1)
        assert idle == 0
    finally:
        disconnect.set()
        await asyncio.wait_for(app_task, timeout=5)
        gate.set()
        await executor.wait(run_id)
        if not app_task.done():
            app_task.cancel()


async def test_citations_survive_a_restart_during_plan_review(client, use_model):
    """El registro de fuentes vive en memoria: al reanudar se reconstruye desde los eventos."""
    from app.agent.sources import release_registry

    await login_through_api(client)
    await _thread(client, mode="research")
    _seed_kb()
    use_model(
        ScriptedChatModel(
            script=[
                ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "r1")]),
                ai("Plan.", [("write_todos", RESEARCH_PLAN, "t1")]),
                ai("Según la guía [1]."),
            ]
        )
    )
    run_id = (await _start(client, mode="research")).json()["run_id"]
    await executor.wait(run_id)
    assert (await _run_row(run_id)).status == "interrupted"

    release_registry(run_id)  # simula el reinicio del proceso
    resumed = await client.post(
        f"/api/v1/runs/{run_id}/resume",
        json={"decision": "approve"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resumed.status_code == 202
    await executor.wait(run_id)

    completed = (await _events(run_id))[-1][2]
    assert completed["text"] == "Plan. Según la guía [1]."
    assert completed["citations"] == [
        {"index": 1, "title": "despliegue", "url": None, "kind": "kb", "snippet": None, "ref": "/kb/despliegue.md"}
    ]
    sources = [p for _, kind, p in await _events(run_id) if kind == "source.added"]
    assert [s["index"] for s in sources] == [1]  # no se duplicó la fuente al reconstruir


async def test_deleting_a_thread_with_a_live_run_is_refused_until_it_settles(client, use_model):
    await login_through_api(client)
    await _thread(client)
    gate = asyncio.Event()
    use_model(GatedChatModel(script=[ai("hola que espera")], gate=gate))
    run_id = (await _start(client)).json()["run_id"]
    headers = {"X-CSRF-Token": csrf_from_client(client)}

    refused = await client.delete("/api/v1/threads/thread-abc", headers=headers)
    assert refused.status_code == 409 and refused.json() == {"detail": "run_active"}

    gate.set()
    await executor.wait(run_id)
    deleted = await client.delete("/api/v1/threads/thread-abc", headers=headers)
    assert deleted.status_code == 204


async def test_orphaned_runs_are_closed_on_startup_but_paused_ones_stay_resumable(client, use_model):
    from app.agent.executor import recover_orphaned_runs
    from tests.helpers import create_user

    user = await create_user(email="orfano@example.com")
    async with async_session_factory() as db:
        thread = Thread(owner_id=user.id, client_id="thread-o", mode="learn")
        db.add(thread)
        await db.flush()
        pairs = []
        for status in ("running", "interrupted"):
            user_msg = Message(thread_id=thread.id, client_id=f"u-{status}", role="user", text="hola", status="complete")
            asst = Message(thread_id=thread.id, client_id=f"a-{status}", role="assistant", text="parcial", status="streaming")
            db.add_all([user_msg, asst])
            await db.flush()
            run = AgentRun(
                thread_id=thread.id,
                user_id=user.id,
                user_message_id=user_msg.id,
                assistant_message_id=asst.id,
                kind="send",
                mode="learn",
                status=status,
            )
            db.add(run)
            await db.flush()
            pairs.append((status, run.id, asst.id))
        await db.commit()

    assert await recover_orphaned_runs() == 1

    async with async_session_factory() as db:
        rows = {status: (await db.get(AgentRun, run_id), await db.get(Message, asst_id)) for status, run_id, asst_id in pairs}
        running, running_msg = rows["running"]
        assert running.status == "failed" and running.error_code == "internal" and running.finished_at is not None
        assert running_msg.status == "error" and running_msg.text == "parcial"
        events = (
            await db.execute(select(AgentRunEvent.type, AgentRunEvent.payload).where(AgentRunEvent.run_id == running.id))
        ).all()
        assert events == [("run.failed", {"error_code": "internal", "message": "The server restarted during the run", "retryable": True})]
        paused, paused_msg = rows["interrupted"]
        assert paused.status == "interrupted" and paused_msg.status == "streaming"
