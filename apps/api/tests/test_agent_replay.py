"""Modo replay (plan B de la demo): el mapa de preguntas reproduce un run grabado sin modelo.

La grabación de los tests es un run real del executor (con modelo falso) o, cuando hace falta
un evento concreto, filas escritas a mano con el mismo formato. Ningún test usa la red.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agent.executor import executor
from app.agent.models import ModelUnavailable, ResolvedModel
from app.agent.replay import RecordedEvent, normalise_prompt, pacing, rebase_payload
from app.db import async_session_factory
from app.models.agent import AgentRun, AgentRunEvent
from app.models.app_setting import AppSetting
from app.models.audit import AuditLog
from app.models.thread import Message, Thread
from tests.agent_fakes import ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import create_user, login_through_api

QUESTION = "¿Qué es un servicio?"
ANSWER = "Un servicio es un programa que atiende peticiones."
TODOS = {"todos": [{"content": "definir", "status": "in_progress"}]}


# --- helpers ----------------------------------------------------------------------------


def _resolved(model) -> ResolvedModel:
    return ResolvedModel(
        chat_model=model,
        label="Modelo de prueba",
        catalog_slug="prueba",
        provider_model_id=None,  # type: ignore[arg-type]
        context_window=32_000,
        input_price=Decimal(1),
        output_price=Decimal(2),
    )


@pytest.fixture
def use_model(monkeypatch):
    def install(model) -> None:
        async def resolver(db, slug):
            return _resolved(model)

        monkeypatch.setattr(executor, "model_resolver", resolver)

    return install


@pytest.fixture
def no_provider(monkeypatch):
    """Ningún modelo disponible: si el replay llamara al catálogo, fallaría."""

    async def unavailable(db, slug):
        raise ModelUnavailable("provider caído (simulado)")

    monkeypatch.setattr(executor, "model_resolver", unavailable)


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


async def _start(client, *, text: str, user_id: str, assistant_id: str, mode: str = "learn") -> str:
    body = {
        "kind": "send",
        "assistant_client_id": assistant_id,
        "mode": mode,
        "model_slug": None,
        "user_message": {"client_id": user_id, "text": text, "attachment_ids": None},
    }
    resp = await client.post(
        "/api/v1/threads/thread-abc/runs",
        json=body,
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["run_id"]


async def _set_replay_map(entries: list[dict[str, Any]]) -> None:
    async with async_session_factory() as db:
        db.add(AppSetting(key="replay.map", value=entries))
        await db.commit()


async def _run_row(run_id: str) -> AgentRun:
    async with async_session_factory() as db:
        return await db.get(AgentRun, uuid.UUID(run_id))


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


async def _answer(client_id: str) -> Message:
    async with async_session_factory() as db:
        return (
            await db.execute(select(Message).where(Message.client_id == client_id))
        ).scalar_one()


async def _replay_audits() -> list[AuditLog]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(AuditLog).where(AuditLog.action == "agent.run_replayed"))).scalars()
        )


async def _record_by_hand(events: list[tuple[str, dict[str, Any]]], *, status: str = "completed") -> str:
    """Un run grabado escrito a mano, con su par de mensajes. Devuelve su id."""
    owner = await create_user(email="grabador@example.com")
    async with async_session_factory() as db:
        thread = Thread(owner_id=owner.id, client_id=f"grabado-{uuid.uuid4()}", mode="research", title="Grabado")
        db.add(thread)
        await db.flush()
        question = Message(thread_id=thread.id, client_id=f"u-{uuid.uuid4()}", role="user", text=QUESTION, status="complete")
        db.add(question)
        await db.flush()
        final = next((payload["text"] for kind, payload in events if kind == "run.completed"), "")
        answer = Message(thread_id=thread.id, client_id=f"a-{uuid.uuid4()}", role="assistant", text=final, status="complete")
        db.add(answer)
        await db.flush()
        run = AgentRun(
            thread_id=thread.id,
            user_id=owner.id,
            user_message_id=question.id,
            assistant_message_id=answer.id,
            kind="send",
            mode="research",
            status=status,
            model_label="Sofee Pro",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        db.add(run)
        await db.flush()
        for seq, (kind, payload) in enumerate(events, start=1):
            db.add(AgentRunEvent(run_id=run.id, seq=seq, type=kind, payload=payload))
        await db.commit()
        return str(run.id)


def _types(events) -> list[str]:
    return [kind for _, kind, _ in events]


# --- normalización y ritmo (funciones puras) --------------------------------------------


def test_prompts_match_regardless_of_case_accents_spacing_and_edge_marks():
    assert normalise_prompt("¿Qué es un servicio?") == "que es un servicio"
    assert normalise_prompt("  que   es  un SERVICIO ") == "que es un servicio"
    assert normalise_prompt("que es un servicio") == normalise_prompt(QUESTION)
    assert normalise_prompt("¿Qué es un servicio? Y más") != normalise_prompt(QUESTION)
    assert normalise_prompt("   ") == ""


def _event(offset_seconds: float | None) -> RecordedEvent:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    stamp = None if offset_seconds is None else base + timedelta(seconds=offset_seconds)
    return RecordedEvent(type="message.delta", payload={}, created_at=stamp)


def test_pacing_keeps_recorded_gaps_and_caps_them_at_two_seconds():
    events = [_event(0), _event(0.5), _event(10.5), _event(9)]
    assert pacing(events) == [0.0, 0.5, 2.0, 0.0]


def test_pacing_without_timestamps_is_instant_and_empty_is_empty():
    assert pacing([_event(None), _event(1)]) == [0.0, 0.0]
    assert pacing([]) == []


def test_rebase_rewrites_only_this_runs_identifiers():
    payload = {"run_id": "viejo", "assistant_message_id": "asst-viejo", "mode": "research", "model_label": "Sofee Pro"}
    rebased = rebase_payload(payload, run_id="nuevo", assistant_id="asst-2", mode="learn")
    assert rebased == {"run_id": "nuevo", "assistant_message_id": "asst-2", "mode": "learn", "model_label": "Sofee Pro"}
    assert payload["run_id"] == "viejo"  # el original no se toca


# --- punta a punta ----------------------------------------------------------------------


async def test_matching_question_replays_the_recording_without_any_model(client, use_model, monkeypatch):
    await login_through_api(client)
    await _thread(client)
    # 1) Un run real, con modelo falso, que servirá de grabación.
    use_model(
        ScriptedChatModel(script=[ai("", [("write_todos", TODOS, "t1")]), ai(ANSWER)])
    )
    recorded_id = await _start(client, text=QUESTION, user_id="user-1", assistant_id="asst-1")
    await executor.wait(recorded_id)
    recorded = await _events(recorded_id)
    recorded_run = await _run_row(recorded_id)
    assert recorded_run.status == "completed"

    # 2) Desde aquí no hay modelo: el replay no debe necesitarlo. La pregunta llega con otra forma.
    async def unavailable(db, slug):
        raise ModelUnavailable("provider caído (simulado)")

    monkeypatch.setattr(executor, "model_resolver", unavailable)
    await _set_replay_map([{"prompt": QUESTION, "run_id": recorded_id}])
    replay_id = await _start(client, text="que es un servicio", user_id="user-2", assistant_id="asst-2")
    await executor.wait(replay_id)

    # 3) El run nuevo emite lo mismo que la grabación, con sus propios ids, y no gasta tokens.
    run = await _run_row(replay_id)
    assert run.status == "completed" and run.finished_at is not None
    assert run.input_tokens == 0 and run.output_tokens == 0 and run.cost_estimate is None
    assert run.model_label == recorded_run.model_label
    replayed = await _events(replay_id)
    assert _types(replayed) == _types(recorded)
    started = replayed[0][2]
    assert started["run_id"] == replay_id and started["assistant_message_id"] == "asst-2"
    assert started["mode"] == "learn"
    assert replayed[-1][2]["text"] == ANSWER

    message = await _answer("asst-2")
    assert message.status == "complete" and message.text == ANSWER

    # 4) Queda auditado qué grabación se reprodujo.
    audits = await _replay_audits()
    assert len(audits) == 1
    assert audits[0].resource_id == replay_id
    assert audits[0].data["recorded_run_id"] == recorded_id


async def test_replay_skips_interrupts_and_completes_without_pausing(client, no_provider):
    await login_through_api(client)
    await _thread(client, mode="research")
    recorded_id = await _record_by_hand(
        [
            ("run.started", {"run_id": "viejo", "assistant_message_id": "a-viejo", "mode": "research", "model_label": "Sofee Pro"}),
            ("interrupt", {"interrupt_id": "i-1", "kind": "plan_review", "todos": [{"content": "buscar", "status": "pending"}]}),
            ("todos.updated", {"items": [{"content": "buscar", "status": "completed"}]}),
            ("message.delta", {"text": "Plan final "}),
            ("message.delta", {"text": "listo."}),
            ("run.completed", {"assistant_message_id": "a-viejo", "text": "Plan final listo.", "citations": []}),
        ]
    )
    await _set_replay_map([{"prompt": "¿Migramos?", "run_id": recorded_id}])
    body = {
        "kind": "send",
        "assistant_client_id": "asst-1",
        "mode": "research",
        "model_slug": None,
        "user_message": {"client_id": "user-1", "text": "¿Migramos?", "attachment_ids": None},
    }
    resp = await client.post(
        "/api/v1/threads/thread-abc/runs", json=body, headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]
    await executor.wait(run_id)

    assert (await _run_row(run_id)).status == "completed"  # nunca queda `interrupted`
    types = _types(await _events(run_id))
    assert "interrupt" not in types
    assert types == ["run.started", "todos.updated", "message.delta", "message.delta", "run.completed"]
    assert (await _answer("asst-1")).text == "Plan final listo."


async def test_recordings_that_did_not_complete_are_not_replayed(client, use_model):
    await login_through_api(client)
    await _thread(client)
    failed_id = await _record_by_hand(
        [("run.started", {"run_id": "viejo", "assistant_message_id": "a", "mode": "learn", "model_label": "x"}),
         ("run.failed", {"error_code": "provider_error", "message": "x", "retryable": True})],
        status="failed",
    )
    await _set_replay_map([{"prompt": QUESTION, "run_id": failed_id}])
    use_model(ScriptedChatModel(script=[ai("En vivo.")]))

    run_id = await _start(client, text=QUESTION, user_id="user-1", assistant_id="asst-1")
    await executor.wait(run_id)

    assert (await _answer("asst-1")).text == "En vivo."
    assert await _replay_audits() == []


async def test_other_questions_and_missing_recordings_answer_live(client, use_model):
    await login_through_api(client)
    await _thread(client)
    await _set_replay_map(
        [
            {"prompt": QUESTION, "run_id": str(uuid.uuid4())},  # el run no existe
            {"prompt": "¿Otra?", "run_id": str(uuid.uuid4())},
        ]
    )
    use_model(ScriptedChatModel(script=[ai("Respuesta en vivo.")]))

    run_id = await _start(client, text=QUESTION, user_id="user-1", assistant_id="asst-1")
    await executor.wait(run_id)

    assert (await _answer("asst-1")).text == "Respuesta en vivo."
    assert await _replay_audits() == []
