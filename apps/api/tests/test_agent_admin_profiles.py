"""Admin de perfiles del agente: versiones, activación única, rollback, validación, RBAC, CSRF y auditoría."""

from copy import deepcopy

from sqlalchemy import func, select

from app.agent.profiles import DEFAULT_PROFILES, load_profile
from app.db import async_session_factory
from app.models.agent import AgentProfile
from app.models.audit import AuditLog
from app.models.user import UserRole
from tests.conftest import csrf_from_client
from tests.helpers import authed_client

BASE = "/api/v1/admin/agent/profiles"


def _headers(client) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_from_client(client)}


async def _versions(mode: str) -> list[AgentProfile]:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(AgentProfile).where(AgentProfile.mode == mode).order_by(AgentProfile.version)
            )
        ).scalars().all()
        return list(rows)


async def _audit(action: str) -> list[AuditLog]:
    async with async_session_factory() as db:
        return list((await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars())


# --- RBAC y CSRF --------------------------------------------------------------------------


async def test_profiles_require_authentication(client):
    assert (await client.get(BASE)).status_code == 401
    resp = await client.post(f"{BASE}/learn", json={"system_prompt": "x"})
    assert resp.status_code == 401


async def test_profiles_are_admin_only(client):
    await authed_client(client, role=UserRole.regular)
    assert (await client.get(BASE)).status_code == 403
    resp = await client.post(
        f"{BASE}/learn",
        json={"system_prompt": "x"},
        headers=_headers(client),
    )
    assert resp.status_code == 403
    resp = await client.post(f"{BASE}/learn/activate/1", headers=_headers(client))
    assert resp.status_code == 403


async def test_mutations_require_csrf(client):
    await authed_client(client)
    assert (await client.post(f"{BASE}/learn", json={"system_prompt": "x"})).status_code == 403
    assert (await client.post(f"{BASE}/learn/activate/1")).status_code == 403


# --- lectura ------------------------------------------------------------------------------


async def test_list_shows_defaults_when_there_is_no_version(client):
    await authed_client(client)
    body = (await client.get(BASE)).json()

    assert [item["mode"] for item in body] == ["learn", "research", "explore"]
    learn = body[0]
    assert learn["active"]["id"] is None
    assert learn["active"]["version"] is None
    assert learn["active"]["is_active"] is True
    assert learn["active"]["system_prompt"] == DEFAULT_PROFILES["learn"]["system_prompt"]
    assert learn["active"]["config"] == DEFAULT_PROFILES["learn"]["config"]
    assert learn["history"] == []


# --- crear versiones ----------------------------------------------------------------------


async def test_create_version_is_active_and_the_agent_loads_it(client):
    admin = await authed_client(client)
    resp = await client.post(
        f"{BASE}/learn",
        json={"system_prompt": "Prompt nuevo del tutor."},
        headers=_headers(client),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["active"]["version"] == 1
    assert body["active"]["is_active"] is True
    assert body["active"]["created_by_email"] == admin.email
    # Sin `config` en la petición, la versión guarda la configuración por defecto completa.
    assert body["active"]["config"] == DEFAULT_PROFILES["learn"]["config"]
    assert [item["version"] for item in body["history"]] == [1]

    async with async_session_factory() as db:
        profile = await load_profile(db, "learn")
    assert profile.system_prompt == "Prompt nuevo del tutor."
    assert profile.version == 1
    assert profile.profile_version_id is not None


async def test_second_version_replaces_the_active_one(client):
    await authed_client(client)
    await client.post(f"{BASE}/explore", json={"system_prompt": "Primera"}, headers=_headers(client))
    resp = await client.post(f"{BASE}/explore", json={"system_prompt": "Segunda"}, headers=_headers(client))

    assert resp.status_code == 201
    body = resp.json()
    assert body["active"]["version"] == 2
    assert [item["version"] for item in body["history"]] == [2, 1]
    assert [item["is_active"] for item in body["history"]] == [True, False]

    versions = await _versions("explore")
    assert sum(1 for version in versions if version.is_active) == 1


async def test_partial_config_is_merged_over_defaults(client):
    await authed_client(client)
    resp = await client.post(
        f"{BASE}/research",
        json={"system_prompt": "Investigación", "config": {"limits": {"max_steps": 25}}},
        headers=_headers(client),
    )

    assert resp.status_code == 201, resp.text
    config = resp.json()["active"]["config"]
    expected = deepcopy(DEFAULT_PROFILES["research"]["config"])
    expected["limits"]["max_steps"] = 25
    assert config == expected


async def test_audit_row_records_the_version(client):
    await authed_client(client)
    await client.post(f"{BASE}/learn", json={"system_prompt": "Uno"}, headers=_headers(client))

    rows = await _audit("agent.profile_version_created")
    assert len(rows) == 1
    assert rows[0].resource_id == "learn"
    assert rows[0].data == {"mode": "learn", "version": 1, "previous_version": None}


# --- validación ---------------------------------------------------------------------------


async def test_invalid_config_is_rejected_and_nothing_is_saved(client):
    await authed_client(client)
    cases = [
        {"tools": ["navegador"]},
        {"unknown_key": True},
        {"limits": {"max_steps": 500}},
        {"limits": {"max_seconds": 5}},
        {"limits": {"surprise": 1}},
        {"planning": False, "plan_review": True},
    ]
    for config in cases:
        resp = await client.post(
            f"{BASE}/learn",
            json={"system_prompt": "x", "config": config},
            headers=_headers(client),
        )
        assert resp.status_code == 422, (config, resp.text)
        assert isinstance(resp.json()["detail"], list)

    assert await _versions("learn") == []


async def test_subagent_names_must_be_unique_and_use_known_tools(client):
    await authed_client(client)
    subagent = {
        "name": "investigador",
        "description": "Busca.",
        "system_prompt": "Busca y resume.",
        "tools": ["web_search"],
        "planning": False,
    }
    duplicated = await client.post(
        f"{BASE}/research",
        json={"system_prompt": "x", "config": {"subagents": [subagent, subagent]}},
        headers=_headers(client),
    )
    assert duplicated.status_code == 422

    unknown_tool = await client.post(
        f"{BASE}/research",
        json={"system_prompt": "x", "config": {"subagents": [{**subagent, "tools": ["borrar_todo"]}]}},
        headers=_headers(client),
    )
    assert unknown_tool.status_code == 422
    assert await _versions("research") == []


async def test_blank_prompt_and_unknown_mode_are_rejected(client):
    await authed_client(client)
    blank = await client.post(f"{BASE}/learn", json={"system_prompt": "   "}, headers=_headers(client))
    assert blank.status_code == 422

    unknown = await client.post(f"{BASE}/chat", json={"system_prompt": "x"}, headers=_headers(client))
    assert unknown.status_code == 404


# --- rollback -----------------------------------------------------------------------------


async def test_activating_an_older_version_is_a_rollback(client):
    await authed_client(client)
    await client.post(f"{BASE}/learn", json={"system_prompt": "Uno"}, headers=_headers(client))
    await client.post(f"{BASE}/learn", json={"system_prompt": "Dos"}, headers=_headers(client))

    resp = await client.post(f"{BASE}/learn/activate/1", headers=_headers(client))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active"]["version"] == 1
    assert body["active"]["system_prompt"] == "Uno"
    assert [item["is_active"] for item in body["history"]] == [False, True]

    async with async_session_factory() as db:
        profile = await load_profile(db, "learn")
    assert profile.system_prompt == "Uno"

    rows = await _audit("agent.profile_version_activated")
    assert len(rows) == 1
    assert rows[0].data == {"mode": "learn", "version": 1, "previous_version": 2}


async def test_activating_an_unknown_version_is_404(client):
    await authed_client(client)
    await client.post(f"{BASE}/learn", json={"system_prompt": "Uno"}, headers=_headers(client))
    resp = await client.post(f"{BASE}/learn/activate/99", headers=_headers(client))
    assert resp.status_code == 404


async def test_only_one_active_version_per_mode_in_the_database(client):
    await authed_client(client)
    for prompt in ("Uno", "Dos", "Tres"):
        await client.post(f"{BASE}/research", json={"system_prompt": prompt}, headers=_headers(client))
    await client.post(f"{BASE}/research/activate/2", headers=_headers(client))

    async with async_session_factory() as db:
        active = (
            await db.execute(
                select(func.count(AgentProfile.id)).where(
                    AgentProfile.mode == "research", AgentProfile.is_active.is_(True)
                )
            )
        ).scalar_one()
    assert active == 1
