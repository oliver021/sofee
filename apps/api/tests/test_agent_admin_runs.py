"""Admin de runs: lista filtrable, detalle con la línea de tiempo, cancelación, valoraciones y panel de uso."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.agent.executor import executor
from app.api.routes.runs_admin import collapse_deltas
from app.db import async_session_factory
from app.models.agent import AgentRun
from app.models.audit import AuditLog
from app.models.feedback import MessageFeedback
from app.models.user import UserRole
from app.services.agent_usage import window_start
from tests.agent_admin_helpers import (
    make_answer_feedback,
    make_model,
    make_provider,
    make_run,
    make_thread,
)
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user

RUNS = "/api/v1/admin/runs"
FEEDBACK = "/api/v1/admin/feedback"
USAGE = "/api/v1/admin/usage"


def _headers(client) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_from_client(client)}


@pytest.fixture(autouse=True)
async def _drain_runs():
    yield
    tasks = list(executor._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _audit(action: str) -> list[AuditLog]:
    async with async_session_factory() as db:
        return list((await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars())


async def _run_row(run_id) -> AgentRun:
    async with async_session_factory() as db:
        return await db.get(AgentRun, run_id)


# --- RBAC y CSRF --------------------------------------------------------------------------


async def test_admin_runs_api_requires_admin(client):
    assert (await client.get(RUNS)).status_code == 401
    await authed_client(client, role=UserRole.regular)
    assert (await client.get(RUNS)).status_code == 403
    assert (await client.get(USAGE)).status_code == 403
    assert (await client.get(FEEDBACK)).status_code == 403


async def test_mutations_require_csrf(client):
    admin = await authed_client(client)
    thread = await make_thread(admin)
    run = await make_run(thread, admin, status="interrupted")
    feedback = await make_answer_feedback(run, admin)

    assert (await client.post(f"{RUNS}/{run.id}/cancel")).status_code == 403
    resp = await client.patch(f"{FEEDBACK}/{feedback.id}", json={"reviewed": True})
    assert resp.status_code == 403


# --- lista --------------------------------------------------------------------------------


async def test_list_shows_newest_first_with_owner_and_metrics(client):
    admin = await authed_client(client)
    owner = await create_user(email="ana@example.com", display_name="Ana")
    thread = await make_thread(owner)
    now = datetime.now(UTC)
    older = await make_run(
        thread, owner, created_at=now - timedelta(hours=2), duration=timedelta(seconds=3),
        input_tokens=100, output_tokens=40, cost=Decimal("0.000123"), catalog_slug="rapido",
    )
    newer = await make_run(thread, owner, created_at=now, mode="research", status="failed", error_code="provider_error")

    resp = await client.get(RUNS)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [item["id"] for item in items] == [str(newer.id), str(older.id)]
    assert items[1]["user_email"] == "ana@example.com"
    assert items[1]["duration_ms"] == 3000
    assert items[1]["cost_estimate"] == pytest.approx(0.000123)
    assert items[0]["error_code"] == "provider_error"
    assert items[0]["mode"] == "research"
    assert str(admin.id) not in str(items)


async def test_filters_by_mode_status_slug_user_and_date(client):
    await authed_client(client)
    owner = await create_user(email="bruno@example.com", display_name="Bruno")
    other = await create_user(email="carla@example.com", display_name="Carla")
    now = datetime.now(UTC)
    thread = await make_thread(owner)
    other_thread = await make_thread(other, client_id="thread-otro")

    research_fail = await make_run(thread, owner, mode="research", status="failed", catalog_slug="profundo", created_at=now)
    learn_ok = await make_run(thread, owner, mode="learn", status="completed", catalog_slug="rapido", created_at=now - timedelta(days=3))
    carla_ok = await make_run(other_thread, other, mode="learn", status="completed", catalog_slug="rapido", created_at=now)

    by_mode = (await client.get(RUNS, params={"mode": "research"})).json()["items"]
    assert [item["id"] for item in by_mode] == [str(research_fail.id)]

    by_status = (await client.get(RUNS, params={"status": "completed"})).json()["items"]
    assert {item["id"] for item in by_status} == {str(learn_ok.id), str(carla_ok.id)}

    by_slug = (await client.get(RUNS, params={"catalog_slug": "profundo"})).json()["items"]
    assert [item["id"] for item in by_slug] == [str(research_fail.id)]

    by_email = (await client.get(RUNS, params={"user": "bruno"})).json()["items"]
    assert {item["user_email"] for item in by_email} == {"bruno@example.com"}

    by_id = (await client.get(RUNS, params={"user": str(other.id)})).json()["items"]
    assert [item["id"] for item in by_id] == [str(carla_ok.id)]

    since = (now - timedelta(days=1)).isoformat()
    recent = (await client.get(RUNS, params={"start": since})).json()["items"]
    assert {item["id"] for item in recent} == {str(research_fail.id), str(carla_ok.id)}


async def test_cursor_pages_through_every_run_once(client):
    await authed_client(client)
    owner = await create_user(email="dani@example.com")
    thread = await make_thread(owner)
    now = datetime.now(UTC)
    created = [
        await make_run(thread, owner, created_at=now - timedelta(minutes=minutes))
        for minutes in range(5)
    ]

    first = (await client.get(RUNS, params={"limit": 2})).json()
    second = (await client.get(RUNS, params={"limit": 2, "cursor": first["next_cursor"]})).json()
    third = (await client.get(RUNS, params={"limit": 2, "cursor": second["next_cursor"]})).json()

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert seen == [str(run.id) for run in created]
    assert third["next_cursor"] is None


async def test_invalid_cursor_is_400(client):
    await authed_client(client)
    resp = await client.get(RUNS, params={"cursor": "no-es-un-cursor"})
    assert resp.status_code == 400


# --- detalle ------------------------------------------------------------------------------


async def test_detail_collapses_deltas_and_shows_question_and_answer(client):
    await authed_client(client)
    owner = await create_user(email="eva@example.com")
    thread = await make_thread(owner)
    run = await make_run(
        thread,
        owner,
        question="¿Qué es un contenedor?",
        answer="Un contenedor empaqueta una aplicación [1].",
        citations=[{"index": 1, "title": "Guía", "url": None, "kind": "kb", "snippet": None, "ref": "doc-1"}],
        events=[
            ("run.started", {"run_id": "r", "assistant_message_id": "a", "mode": "learn", "model_label": "X"}),
            ("message.delta", {"text": "Un contenedor "}),
            ("message.delta", {"text": "empaqueta "}),
            ("tool.started", {"id": "t1", "name": "search_team_docs", "agent": "main", "args_preview": "{}"}),
            ("message.delta", {"text": "una aplicación [1]."}),
            ("run.completed", {"assistant_message_id": "a", "text": "x", "citations": []}),
        ],
    )

    resp = await client.get(f"{RUNS}/{run.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["question"] == "¿Qué es un contenedor?"
    assert body["answer"] == "Un contenedor empaqueta una aplicación [1]."
    assert body["citations"][0]["ref"] == "doc-1"
    assert body["trace_url"] is None
    assert body["profile_version"] is None

    types = [event["type"] for event in body["events"]]
    assert types == ["run.started", "message.delta", "tool.started", "run.completed"]
    delta = body["events"][1]
    assert delta["payload"] == {"text": "Un contenedor empaqueta una aplicación [1].", "chunks": 3}


async def test_detail_unknown_or_malformed_run_id(client):
    await authed_client(client)
    assert (await client.get(f"{RUNS}/{uuid.uuid4()}")).status_code == 404
    assert (await client.get(f"{RUNS}/no-es-uuid")).status_code == 422


def test_collapse_deltas_keeps_position_of_first_delta_and_order_of_the_rest():
    rows = [
        (1, "run.started", {}),
        (2, "message.delta", {"text": "Hola"}),
        (3, "tool.started", {"name": "x"}),
        (4, "message.delta", {"text": " mundo"}),
        (5, "run.completed", {}),
    ]
    events = collapse_deltas(rows)
    assert [(event.seq, event.type) for event in events] == [
        (1, "run.started"),
        (2, "message.delta"),
        (3, "tool.started"),
        (5, "run.completed"),
    ]
    assert events[1].payload == {"text": "Hola mundo", "chunks": 2}


def test_collapse_deltas_without_deltas_is_unchanged():
    rows = [(1, "run.started", {"a": 1}), (2, "usage", {"input_tokens": 3})]
    assert [event.payload for event in collapse_deltas(rows)] == [{"a": 1}, {"input_tokens": 3}]


# --- cancelación --------------------------------------------------------------------------


async def test_admin_cancels_any_active_run_and_it_is_audited(client):
    admin = await authed_client(client)
    owner = await create_user(email="fer@example.com")
    thread = await make_thread(owner)
    run = await make_run(thread, owner, status="interrupted", answer="Parcial")

    resp = await client.post(f"{RUNS}/{run.id}/cancel", headers=_headers(client))

    assert resp.status_code == 202
    refreshed = await _run_row(run.id)
    assert refreshed.status == "cancelled"
    rows = await _audit("agent.run_cancelled")
    assert len(rows) == 1
    assert rows[0].actor_id == admin.id
    assert rows[0].data["scope"] == "admin"
    assert rows[0].data["previous_status"] == "interrupted"


async def test_cancelling_a_finished_run_is_idempotent_and_not_audited(client):
    await authed_client(client)
    owner = await create_user(email="gina@example.com")
    thread = await make_thread(owner)
    run = await make_run(thread, owner, status="completed")

    resp = await client.post(f"{RUNS}/{run.id}/cancel", headers=_headers(client))

    assert resp.status_code == 202
    assert (await _run_row(run.id)).status == "completed"
    assert await _audit("agent.run_cancelled") == []


async def test_cancel_unknown_run_is_404(client):
    await authed_client(client)
    resp = await client.post(f"{RUNS}/{uuid.uuid4()}/cancel", headers=_headers(client))
    assert resp.status_code == 404


# --- valoraciones -------------------------------------------------------------------------


async def test_feedback_list_carries_question_answer_and_run(client):
    await authed_client(client)
    owner = await create_user(email="hugo@example.com")
    thread = await make_thread(owner)
    run = await make_run(thread, owner, question="¿Qué es un puerto?", answer="Un puerto es un número.")
    await make_answer_feedback(run, owner, value="bad", reason="incorrecta", comment="Falta contexto")

    resp = await client.get(FEEDBACK)

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["value"] == "bad"
    assert item["reason"] == "incorrecta"
    assert item["comment"] == "Falta contexto"
    assert item["question"] == "¿Qué es un puerto?"
    assert item["answer"] == "Un puerto es un número."
    assert item["run_id"] == str(run.id)
    assert item["user_email"] == "hugo@example.com"
    assert item["reviewed"] is False


async def test_feedback_filters_and_review_toggle(client):
    admin = await authed_client(client)
    owner = await create_user(email="ivan@example.com")
    thread = await make_thread(owner)
    bad = await make_answer_feedback(await make_run(thread, owner, answer="A"), owner, value="bad")
    good = await make_answer_feedback(
        await make_run(thread, owner, answer="B", question="¿B?"), owner, value="good", reason=None
    )

    only_bad = (await client.get(FEEDBACK, params={"value": "bad"})).json()["items"]
    assert [item["id"] for item in only_bad] == [str(bad.id)]

    resp = await client.patch(f"{FEEDBACK}/{bad.id}", json={"reviewed": True}, headers=_headers(client))
    assert resp.status_code == 200, resp.text
    assert resp.json()["reviewed"] is True
    assert resp.json()["reviewed_at"] is not None

    pending = (await client.get(FEEDBACK, params={"reviewed": False})).json()["items"]
    assert [item["id"] for item in pending] == [str(good.id)]
    reviewed = (await client.get(FEEDBACK, params={"reviewed": True})).json()["items"]
    assert [item["id"] for item in reviewed] == [str(bad.id)]

    back = await client.patch(f"{FEEDBACK}/{bad.id}", json={"reviewed": False}, headers=_headers(client))
    assert back.json()["reviewed"] is False

    rows = await _audit("agent.feedback_reviewed")
    assert [row.data["reviewed"] for row in rows] == [True, False]
    assert all(row.actor_id == admin.id for row in rows)


async def test_feedback_patch_unknown_id_and_bad_value_filter(client):
    await authed_client(client)
    missing = await client.patch(f"{FEEDBACK}/{uuid.uuid4()}", json={"reviewed": True}, headers=_headers(client))
    assert missing.status_code == 404
    bad_filter = await client.get(FEEDBACK, params={"value": "meh"})
    assert bad_filter.status_code == 422


async def test_feedback_row_is_stored_for_the_message(client):
    await authed_client(client)
    owner = await create_user(email="jose@example.com")
    thread = await make_thread(owner)
    run = await make_run(thread, owner)
    feedback = await make_answer_feedback(run, owner)

    async with async_session_factory() as db:
        stored = await db.get(MessageFeedback, feedback.id)
    assert stored.message_id == run.assistant_message_id


# --- uso ----------------------------------------------------------------------------------


def test_window_starts_at_utc_midnight_of_the_first_day():
    now = datetime(2026, 10, 29, 15, 30, tzinfo=UTC)
    assert window_start(1, now) == datetime(2026, 10, 29, tzinfo=UTC)
    assert window_start(7, now) == datetime(2026, 10, 23, tzinfo=UTC)


async def test_usage_totals_percentiles_and_bindings(client):
    await authed_client(client)
    owner = await create_user(email="kim@example.com")
    thread = await make_thread(owner)
    provider = await make_provider("DeepInfra")
    model_a = await make_model(provider, "modelo-a", supports_tools=True)
    model_b = await make_model(provider, "modelo-b", supports_tools=True)
    now = datetime.now(UTC)

    await make_run(
        thread, owner, created_at=now, duration=timedelta(seconds=2), input_tokens=100, output_tokens=50,
        cost=Decimal("0.001"), ttft_ms=300, catalog_slug="rapido", model_label="Rápido",
        provider_model_id=model_a.id, hallucinated=1,
    )
    await make_run(
        thread, owner, created_at=now, duration=timedelta(seconds=4), input_tokens=10, output_tokens=0,
        status="failed", error_code="provider_error", catalog_slug="rapido", model_label="Rápido",
        provider_model_id=model_a.id,
    )
    await make_run(
        thread, owner, created_at=now, duration=timedelta(seconds=6), input_tokens=200, output_tokens=100,
        cost=Decimal("0.002"), ttft_ms=500, catalog_slug="profundo", model_label="Profundo",
        provider_model_id=model_b.id,
    )
    # Fuera de la ventana de 7 días: no cuenta.
    await make_run(thread, owner, created_at=now - timedelta(days=10), input_tokens=999, output_tokens=999)

    resp = await client.get(USAGE, params={"days": 7})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    totals = body["totals"]
    assert totals["runs"] == 3
    assert totals["input_tokens"] == 310
    assert totals["output_tokens"] == 150
    assert totals["cost_estimate"] == pytest.approx(0.003)
    assert totals["failed_runs"] == 1
    assert totals["error_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert totals["hallucinated_citations"] == 1

    # Duraciones 2 s, 4 s y 6 s; ttft 300 ms y 500 ms.
    assert body["latency"]["duration_p50_ms"] == pytest.approx(4000.0)
    assert body["latency"]["duration_p95_ms"] == pytest.approx(5800.0)
    assert body["latency"]["ttft_p50_ms"] == pytest.approx(400.0)

    by_model = {row["catalog_slug"]: row for row in body["by_model"]}
    assert by_model["rapido"]["runs"] == 2
    assert by_model["profundo"]["output_tokens"] == 100
    assert sum(row["runs"] for row in body["daily"]) == 3
    assert {row["day"] for row in body["daily"]} == {now.date().isoformat()}

    bindings = {row["model_id"]: row for row in body["bindings"]}
    assert bindings["modelo-a"]["runs"] == 2
    assert bindings["modelo-a"]["error_rate"] == pytest.approx(0.5)
    assert bindings["modelo-b"]["error_rate"] == pytest.approx(0.0)
    assert bindings["modelo-b"]["provider_name"] == "DeepInfra"


async def test_usage_window_validation_and_empty_data(client):
    await authed_client(client)
    assert (await client.get(USAGE, params={"days": 0})).status_code == 422
    assert (await client.get(USAGE, params={"days": 91})).status_code == 422

    body = (await client.get(USAGE)).json()
    assert body["days"] == 7
    assert body["totals"]["runs"] == 0
    assert body["totals"]["error_rate"] is None
    assert body["latency"]["duration_p50_ms"] is None
    assert body["daily"] == [] and body["bindings"] == []


async def test_run_cost_is_stored_as_decimal(client):
    admin = await authed_client(client)
    thread = await make_thread(admin)
    run = await make_run(thread, admin, cost=Decimal("0.000450"))
    assert (await _run_row(run.id)).cost_estimate == Decimal("0.000450")
