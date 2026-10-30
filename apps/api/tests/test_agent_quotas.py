"""Cuotas por rol (runs y tokens por día) en la creación de runs, configuradas desde el admin.

El 429 llega antes de crear nada y su `reset_at` es la medianoche UTC siguiente. Modelos con guion,
sin red.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.agent.executor import executor
from app.agent.models import ResolvedModel
from app.db import async_session_factory
from app.models.agent import AgentRun
from app.models.user import User, UserRole
from tests.agent_fakes import ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import create_user, insert_session

SETTINGS = "/api/v1/admin/agent/settings"


@pytest.fixture
def use_model(monkeypatch):
    def install(model) -> None:
        async def resolver(db, slug):
            return ResolvedModel(
                chat_model=model,
                label="Modelo de prueba",
                catalog_slug="prueba",
                provider_model_id=None,  # type: ignore[arg-type]
                context_window=32_000,
                input_price=Decimal(1),
                output_price=Decimal(2),
            )

        monkeypatch.setattr(executor, "model_resolver", resolver)

    return install


@pytest.fixture(autouse=True)
async def _drain_runs():
    yield
    tasks = list(executor._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _login_as(client, user: User) -> None:
    """Cambia la sesión del cliente a la de `user` (una sesión nueva por cambio)."""
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))


def _headers(client) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_from_client(client)}


async def _people() -> tuple[User, User]:
    admin = await create_user(email="admin@example.com", role=UserRole.admin)
    student = await create_user(email="estudiante@example.com", role=UserRole.regular)
    return admin, student


async def _thread_as(client, user: User, client_id: str = "thread-abc") -> None:
    await _login_as(client, user)
    resp = await client.post(
        "/api/v1/threads",
        json={"client_id": client_id, "mode": "learn"},
        headers=_headers(client),
    )
    assert resp.status_code == 201, resp.text


async def _set_quotas(client, admin: User, quotas: dict) -> None:
    await _login_as(client, admin)
    current = (await client.get(SETTINGS)).json()
    current["quotas"] = quotas
    resp = await client.put(SETTINGS, json=current, headers=_headers(client))
    assert resp.status_code == 200, resp.text


async def _start(client, *, n: int, thread: str = "thread-abc"):
    return await client.post(
        f"/api/v1/threads/{thread}/runs",
        json={
            "kind": "send",
            "assistant_client_id": f"asst-{n}",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": f"user-{n}", "text": f"Pregunta {n}", "attachment_ids": None},
        },
        headers=_headers(client),
    )


async def _run_count() -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count(AgentRun.id)))).scalar_one()


def _next_utc_midnight() -> datetime:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=1)


async def test_runs_per_day_answers_429_with_next_utc_midnight(client, use_model):
    admin, student = await _people()
    await _set_quotas(client, admin, {"regular": {"runs_per_day": 1}})
    await _thread_as(client, student)
    use_model(ScriptedChatModel(script=[ai("uno"), ai("dos")]))

    first = await _start(client, n=1)
    assert first.status_code == 201, first.text
    await executor.wait(first.json()["run_id"])
    runs_before = await _run_count()

    second = await _start(client, n=2)

    assert second.status_code == 429
    body = second.json()
    assert body["detail"] == "quota_exceeded"
    reset_at = datetime.fromisoformat(body["reset_at"])
    assert reset_at == _next_utc_midnight()
    assert reset_at.utcoffset() == timedelta(0)
    # Un 429 no crea el run ni el mensaje del usuario.
    assert await _run_count() == runs_before


async def test_tokens_per_day_blocks_the_next_run(client, use_model):
    admin, student = await _people()
    await _set_quotas(client, admin, {"regular": {"tokens_per_day": 10}})
    await _thread_as(client, student)
    use_model(ScriptedChatModel(script=[ai("uno", input_tokens=10, output_tokens=5), ai("dos")]))

    first = await _start(client, n=1)
    await executor.wait(first.json()["run_id"])
    second = await _start(client, n=2)

    assert second.status_code == 429
    assert second.json()["detail"] == "quota_exceeded"


async def test_the_quota_applies_per_user_across_threads(client, use_model):
    admin, student = await _people()
    await _set_quotas(client, admin, {"regular": {"runs_per_day": 1}})
    await _thread_as(client, student, client_id="thread-uno")
    await _thread_as(client, student, client_id="thread-dos")
    use_model(ScriptedChatModel(script=[ai("uno")]))

    first = await _start(client, n=1, thread="thread-uno")
    await executor.wait(first.json()["run_id"])
    other_thread = await _start(client, n=2, thread="thread-dos")

    assert other_thread.status_code == 429


async def test_admin_role_has_its_own_limits(client, use_model):
    admin, _student = await _people()
    await _set_quotas(client, admin, {"regular": {"runs_per_day": 1}, "admin": {"runs_per_day": 5}})
    await _thread_as(client, admin)
    use_model(ScriptedChatModel(script=[ai("uno"), ai("dos")]))

    first = await _start(client, n=1)
    await executor.wait(first.json()["run_id"])
    second = await _start(client, n=2)

    assert second.status_code == 201, second.text


async def test_without_quotas_runs_are_not_limited(client, use_model):
    _admin, student = await _people()
    await _thread_as(client, student)
    use_model(ScriptedChatModel(script=[ai("uno"), ai("dos"), ai("tres")]))

    for n in range(1, 4):
        resp = await _start(client, n=n)
        assert resp.status_code == 201, resp.text
        await executor.wait(resp.json()["run_id"])


async def test_zero_runs_per_day_blocks_the_role_entirely(client, use_model):
    admin, student = await _people()
    await _set_quotas(client, admin, {"regular": {"runs_per_day": 0}})
    await _thread_as(client, student)
    use_model(ScriptedChatModel(script=[ai("uno")]))

    resp = await _start(client, n=1)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "quota_exceeded"
