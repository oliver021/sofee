"""Ajustes del agente en el admin: GET/PUT, validación, auditoría y efecto en el agente real."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import async_session_factory
from app.models.app_setting import AppSetting
from app.models.audit import AuditLog
from app.models.user import UserRole
from tests.agent_admin_helpers import make_run, make_thread
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user

BASE = "/api/v1/admin/agent/settings"


def _headers(client) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_from_client(client)}


def _body(**overrides) -> dict:
    body = {"enabled": True, "starters": {}, "replay_map": [], "quotas": {}}
    body.update(overrides)
    return body


async def _setting(key: str):
    async with async_session_factory() as db:
        row = await db.get(AppSetting, key)
        return None if row is None else row.value


# --- RBAC y CSRF --------------------------------------------------------------------------


async def test_settings_require_authentication_and_admin(client):
    assert (await client.get(BASE)).status_code == 401
    await authed_client(client, role=UserRole.regular)
    assert (await client.get(BASE)).status_code == 403
    assert (await client.put(BASE, json=_body(), headers=_headers(client))).status_code == 403


async def test_put_requires_csrf(client):
    await authed_client(client)
    assert (await client.put(BASE, json=_body())).status_code == 403


# --- lectura y escritura ------------------------------------------------------------------


async def test_get_returns_defaults_when_nothing_is_stored(client):
    await authed_client(client)
    resp = await client.get(BASE)
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True, "starters": {}, "replay_map": [], "quotas": {}}


async def test_put_stores_all_four_keys_and_audits_the_change(client):
    admin = await authed_client(client)
    owner = await create_user(email="demo@example.com")
    thread = await make_thread(owner)
    run = await make_run(thread, owner, created_at=datetime.now(UTC))
    body = _body(
        enabled=False,
        starters={"learn": {"es": ["¿Qué es un servicio?", "  ¿Qué es Docker?  "]}, "explore": {"en": ["What now?"]}},
        replay_map=[{"prompt": "Demo de Research", "run_id": str(run.id)}],
        quotas={"regular": {"runs_per_day": 20, "tokens_per_day": 100000}, "admin": {}},
    )

    resp = await client.put(BASE, json=body, headers=_headers(client))

    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["enabled"] is False
    assert saved["starters"] == {"learn": {"es": ["¿Qué es un servicio?", "¿Qué es Docker?"]}, "explore": {"en": ["What now?"]}}
    assert saved["replay_map"] == [{"prompt": "Demo de Research", "run_id": str(run.id)}]
    assert saved["quotas"]["regular"] == {"runs_per_day": 20, "tokens_per_day": 100000}

    assert await _setting("agent.enabled") is False
    assert await _setting("replay.map") == [{"prompt": "Demo de Research", "run_id": str(run.id)}]
    assert (await _setting("quotas"))["regular"] == {"runs_per_day": 20, "tokens_per_day": 100000}
    assert (await _setting("starters"))["learn"]["es"][1] == "¿Qué es Docker?"

    async with async_session_factory() as db:
        rows = list((await db.execute(select(AuditLog).where(AuditLog.action == "agent.settings_updated"))).scalars())
    assert len(rows) == 1
    assert rows[0].actor_id == admin.id
    assert set(rows[0].data["changed"]) == {"agent.enabled", "starters", "replay.map", "quotas"}


async def test_put_replaces_the_whole_document(client):
    await authed_client(client)
    await client.put(BASE, json=_body(starters={"learn": {"es": ["Uno"]}}), headers=_headers(client))
    resp = await client.put(BASE, json=_body(), headers=_headers(client))
    assert resp.json()["starters"] == {}


async def test_put_without_every_field_is_rejected(client):
    await authed_client(client)
    resp = await client.put(BASE, json={"enabled": True}, headers=_headers(client))
    assert resp.status_code == 422


# --- validación ---------------------------------------------------------------------------


async def test_invalid_settings_are_rejected(client):
    await authed_client(client)
    invalid_bodies = [
        _body(starters={"chat": {"es": ["x"]}}),
        _body(starters={"learn": {"ES_x": ["x"]}}),
        _body(starters={"learn": {"es": ["x"] * 11}}),
        _body(starters={"learn": {"es": ["   "]}}),
        _body(quotas={"root": {"runs_per_day": 1}}),
        _body(quotas={"regular": {"runs_per_day": -1}}),
        _body(quotas={"regular": {"por_hora": 3}}),
        _body(replay_map=[{"prompt": "", "run_id": str(uuid.uuid4())}]),
    ]
    for body in invalid_bodies:
        resp = await client.put(BASE, json=body, headers=_headers(client))
        assert resp.status_code == 422, (body, resp.text)

    assert await _setting("agent.enabled") is None


async def test_replay_map_must_point_to_existing_runs(client):
    await authed_client(client)
    missing = str(uuid.uuid4())
    resp = await client.put(
        BASE,
        json=_body(replay_map=[{"prompt": "Demo", "run_id": missing}]),
        headers=_headers(client),
    )
    assert resp.status_code == 422
    assert missing in resp.json()["detail"]


# --- efecto en el agente ------------------------------------------------------------------


async def test_kill_switch_stops_new_runs_immediately(client):
    admin = await authed_client(client, role=UserRole.admin)
    thread = await make_thread(admin)

    await client.put(BASE, json=_body(enabled=False), headers=_headers(client))
    resp = await client.post(
        f"/api/v1/threads/{thread.client_id}/runs",
        json={
            "kind": "send",
            "assistant_client_id": "asst-1",
            "mode": "learn",
            "model_slug": None,
            "user_message": {"client_id": "user-1", "text": "Hola", "attachment_ids": None},
        },
        headers=_headers(client),
    )
    assert resp.status_code == 503
    assert resp.json() == {"detail": "agent_disabled"}


async def test_published_starters_reach_the_public_endpoint(client):
    await authed_client(client)
    await client.put(
        BASE,
        json=_body(starters={"learn": {"es": ["¿Qué es una API?", "¿Qué es un contenedor?"]}}),
        headers=_headers(client),
    )

    resp = await client.get("/api/v1/starters?mode=learn&locale=es")
    assert resp.status_code == 200
    assert [item["text"] for item in resp.json()] == ["¿Qué es una API?", "¿Qué es un contenedor?"]

    other_locale = await client.get("/api/v1/starters?mode=learn&locale=en")
    assert other_locale.json() == []
