"""Piezas sueltas del B2: qué herramientas se ofrecen, el límite de subagentes, la forma de la
copia de /kb/ en el store y la reconstrucción del presupuesto al reanudar."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest_asyncio
from langchain_core.messages import ToolMessage

from app.agent.executor import _RunState, executor
from app.agent.knowledge import mirror_document, store_key, unmirror_document
from app.agent.limits import SubagentLimitMiddleware
from app.agent.persistence import get_agent_storage
from app.agent.sources import get_registry, release_registry
from app.agent.tools import get_tools
from app.models.kb import KbDocument
from app.services.knowledge import kb_path
from tests.agent_fakes import ScriptedChatModel, ai
from tests.helpers import authed_client

# Mismos helpers y fixture de run que test_knowledge_runs.py.
from tests.test_knowledge_runs import _events, _start, _thread, _upload_kb, use_model  # noqa: F401

EXPLORE = {"tools": ["search_team_docs", "web_search", "suggest_directions"], "limits": {"max_searches": 3}}


@pytest_asyncio.fixture(autouse=True)
async def _drain_runs():
    yield
    tasks = list(executor._tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _names(tools) -> list[str]:
    return [tool.name for tool in tools]


def test_web_search_is_offered_only_when_tavily_is_configured():
    assert _names(get_tools("explore", EXPLORE, web_search=False)) == ["search_team_docs", "suggest_directions"]
    assert _names(get_tools("explore", EXPLORE, web_search=True)) == [
        "search_team_docs",
        "web_search",
        "suggest_directions",
    ]


def test_get_tools_keeps_the_profile_order_and_skips_unknown_names():
    config = {"tools": ["suggest_directions", "no_existe", "search_team_docs"], "subagents": [{"tools": ["search_team_docs"]}]}
    assert _names(get_tools("learn", config)) == ["suggest_directions", "search_team_docs"]


def _fake_request(name: str, run_id: str, call_id: str = "k1"):
    return SimpleNamespace(
        tool_call={"name": name, "args": {}, "id": call_id},
        runtime=SimpleNamespace(context=SimpleNamespace(run_id=run_id)),
    )


async def test_subagent_limit_refuses_calls_past_the_profile_budget():
    middleware = SubagentLimitMiddleware(max_subagents=2)
    calls: list[str] = []

    async def handler(request):  # noqa: ANN001, ANN202
        calls.append(request.tool_call["id"])
        return ToolMessage(content="ok", tool_call_id=request.tool_call["id"], name="task")

    run_id = "run-limit-test"
    release_registry(run_id)
    results = [
        await middleware.awrap_tool_call(_fake_request("task", run_id, f"k{i}"), handler) for i in range(3)
    ]
    assert [r.status for r in results[:2]] == ["success", "success"]
    refused = results[2]
    assert refused.status == "error" and "límite de 2 subagentes" in refused.content
    assert calls == ["k0", "k1"]
    # Otras herramientas no cuentan ni se bloquean.
    other = await middleware.awrap_tool_call(_fake_request("read_file", run_id), handler)
    assert other.content == "ok"
    assert get_registry(run_id).subagents == 3
    release_registry(run_id)


async def test_kb_documents_are_mirrored_with_the_store_backend_value_shape():
    document = KbDocument(
        slug="guia",
        title="Guía",
        path=kb_path("guia"),
        source_filename="guia.md",
        content_type="text/markdown",
        text="# Guía\n\nTexto.",
        tags=[],
        is_enabled=True,
        size_bytes=15,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    store = get_agent_storage().store
    await mirror_document(store, document)
    item = await store.aget(("kb",), store_key("guia"))
    assert set(item.value) == {"content", "encoding", "created_at", "modified_at"}
    assert item.value["content"] == "# Guía\n\nTexto." and item.value["encoding"] == "utf-8"
    assert item.value["created_at"] == "2026-01-02T00:00:00+00:00"
    assert store_key("guia") == "/guia.md"
    await unmirror_document(store, "guia")
    assert await store.aget(("kb",), "/guia.md") is None


async def test_the_search_budget_is_rebuilt_from_persisted_events_after_a_restart(client, use_model):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", "# Despliegue\n\nEl pipeline del equipo.")
    await _thread(client, mode="explore")
    use_model(
        ScriptedChatModel(
            script=[
                ai("", [("search_team_docs", {"query": "pipeline"}, "s1")]),
                ai("", [("search_team_docs", {"query": "equipo"}, "s2")]),
                ai("Listo [1]."),
            ]
        )
    )
    run_id = (await _start(client, mode="explore")).json()["run_id"]
    await executor.wait(run_id)
    finished = [p for k, p in await _events(run_id) if k == "tool.finished"]
    assert [p["status"] for p in finished] == ["success", "success"]

    # Simula un reinicio: el registro en memoria desaparece y el estado se carga desde la BD.
    release_registry(run_id)
    state = _RunState(run_id=run_id)
    await executor._ensure_loaded(state)
    assert get_registry(run_id).searches == 2
    assert get_registry(run_id).subagents == 0
    release_registry(run_id)
