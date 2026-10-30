import uuid
from copy import deepcopy

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from app.agent.backends import make_backend
from app.agent.context import SofeeContext
from app.agent.models import ResolvedModel
from app.agent.profiles import DEFAULT_PROFILES, MODES, ProfileSpec, build_agent, load_profile
from app.agent.sources import finalize, get_registry, release_registry
from app.agent.tools import get_tools
from app.db import async_session_factory
from app.models.agent import AgentProfile as AgentProfileVersion
from tests.agent_fakes import FailingChatModel, ScriptedChatModel, ai

DESPLIEGUE_DOC = "# Despliegue\n\nSe despliega con el pipeline del equipo."


def _resolved(chat_model, fallbacks=()):
    return ResolvedModel(
        chat_model=chat_model,
        label="Modelo de prueba",
        catalog_slug="prueba",
        provider_model_id=uuid.uuid4(),
        context_window=32_000,
        input_price=None,
        output_price=None,
        fallback_models=tuple(fallbacks),
    )


def _profile(mode: str) -> ProfileSpec:
    defaults = DEFAULT_PROFILES[mode]
    return ProfileSpec(mode=mode, system_prompt=defaults["system_prompt"], config=deepcopy(defaults["config"]))


def _agent(mode, model, *, subagent_model=None, fallbacks=(), store=None, checkpointer=None):
    profile = _profile(mode)
    return build_agent(
        profile,
        _resolved(model, fallbacks),
        get_tools(mode, profile.config),
        make_backend(),
        checkpointer or InMemorySaver(),
        store or InMemoryStore(),
        subagent_model=subagent_model,
    )


def _ctx(mode: str, thread_id: str | None = None) -> SofeeContext:
    return SofeeContext(
        user_id="user-1",
        thread_id=thread_id or str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        mode=mode,
        locale="es",
    )


async def _invoke(agent, text, ctx, cfg, resume=None):
    inputs = resume if resume is not None else {"messages": [{"role": "user", "content": text}]}
    return await agent.ainvoke(inputs, cfg, context=ctx, version="v2")


async def _tool_messages(agent, text, ctx, cfg):
    """Mensajes de herramienta de todo el run, también de los subagentes (ns no vacío)."""
    found = []
    async for part in agent.astream(
        {"messages": [{"role": "user", "content": text}]},
        cfg,
        context=ctx,
        stream_mode="updates",
        subgraphs=True,
        version="v2",
    ):
        if part["type"] != "updates":
            continue
        for update in part["data"].values():
            if isinstance(update, dict):
                for message in update.get("messages", []) or []:
                    if isinstance(message, ToolMessage):
                        found.append(message)
    return found


async def _store_run_once(store, namespace, key, text):
    store.put(namespace, key, {"content": text, "encoding": "utf-8"})


# --- defaults y compilación -------------------------------------------------------


def test_defaults_cover_the_three_modes_with_roadmap_shape():
    assert MODES == ("learn", "research", "explore")
    research = DEFAULT_PROFILES["research"]["config"]
    assert [s["name"] for s in research["subagents"]] == ["investigador", "critico"]
    assert research["plan_review"] is True
    assert research["limits"]["max_subagents"] == 3
    assert research["limits"]["max_searches"] == 12
    assert DEFAULT_PROFILES["learn"]["config"]["subagents"] == []
    assert DEFAULT_PROFILES["explore"]["config"]["subagents"] == []
    assert DEFAULT_PROFILES["explore"]["config"]["planning"] is False
    for mode in MODES:
        prompt = DEFAULT_PROFILES[mode]["system_prompt"]
        assert "Never invent" in prompt or "never invent" in prompt.lower()
        assert "/notes/" in prompt


def test_build_agent_compiles_for_all_modes():
    for mode in MODES:
        agent = _agent(mode, ScriptedChatModel(script=[ai("hola")]))
        assert agent is not None
        assert hasattr(agent, "ainvoke")


async def test_general_purpose_subagent_is_disabled():
    model = ScriptedChatModel(
        script=[
            ai("", [("task", {"description": "x", "subagent_type": "general-purpose"}, "k1")]),
            ai("fin"),
        ]
    )
    agent = _agent("research", model)
    ctx = _ctx("research")
    messages = await _tool_messages(agent, "pregunta", ctx, {"configurable": {"thread_id": ctx.run_id}})
    task_results = [m.content for m in messages if m.name == "task"]
    assert task_results
    assert "the only allowed types are `investigador`, `critico`" in task_results[0]


# --- perfiles en BD ---------------------------------------------------------------


async def test_load_profile_without_row_returns_code_defaults():
    async with async_session_factory() as db:
        profile = await load_profile(db, "learn")
    assert profile.version is None
    assert profile.profile_version_id is None
    assert profile.config == DEFAULT_PROFILES["learn"]["config"]


async def test_load_profile_merges_active_version_over_defaults():
    async with async_session_factory() as db:
        row = AgentProfileVersion(
            mode="learn",
            version=2,
            is_active=True,
            system_prompt="Prompt editado por el admin.",
            config={"limits": {"max_steps": 99}, "planning": False},
        )
        db.add(row)
        await db.commit()
        row_id = row.id

    async with async_session_factory() as db:
        profile = await load_profile(db, "learn")
    assert profile.version == 2
    assert profile.profile_version_id == row_id
    assert profile.system_prompt == "Prompt editado por el admin."
    assert profile.config["limits"] == {**DEFAULT_PROFILES["learn"]["config"]["limits"], "max_steps": 99}
    assert profile.config["planning"] is False
    assert profile.config["tools"] == DEFAULT_PROFILES["learn"]["config"]["tools"]


# --- runs de punta a punta --------------------------------------------------------


async def test_learn_plans_with_write_todos_and_answers():
    model = ScriptedChatModel(
        script=[
            ai("", [("write_todos", {"todos": [{"content": "definir", "status": "in_progress"}]}, "t1")]),
            ai("Una definición corta."),
        ]
    )
    agent = _agent("learn", model)
    ctx = _ctx("learn")
    cfg = {"configurable": {"thread_id": ctx.run_id}}
    result = await _invoke(agent, "¿Qué es un servicio?", ctx, cfg)
    assert result.interrupts == ()
    assert result.value["messages"][-1].content.strip() == "Una definición corta."
    assert result.value["todos"] == [{"content": "definir", "status": "in_progress"}]


async def test_research_interrupts_first_plan_once_then_resumes():
    model = ScriptedChatModel(
        script=[
            ai("", [("write_todos", {"todos": [{"content": "buscar", "status": "pending"}]}, "t1")]),
            ai("", [("write_todos", {"todos": [{"content": "buscar", "status": "completed"}]}, "t2")]),
            ai("Informe listo."),
        ]
    )
    agent = _agent("research", model)
    ctx = _ctx("research")
    cfg = {"configurable": {"thread_id": ctx.run_id}}

    first = await _invoke(agent, "¿Migramos?", ctx, cfg)
    assert len(first.interrupts) == 1
    request = first.interrupts[0].value["action_requests"][0]
    assert request["name"] == "write_todos"

    done = await _invoke(
        agent,
        "",
        ctx,
        cfg,
        resume=Command(resume={"decisions": [{"type": "approve"}]}),
    )
    assert done.interrupts == ()
    assert done.value["messages"][-1].content.strip() == "Informe listo."
    assert done.value["todos"] == [{"content": "buscar", "status": "completed"}]


async def test_resume_with_edit_replaces_the_plan():
    model = ScriptedChatModel(
        script=[
            ai("", [("write_todos", {"todos": [{"content": "original", "status": "pending"}]}, "t1")]),
            ai("Listo con el plan editado."),
        ]
    )
    agent = _agent("research", model)
    ctx = _ctx("research")
    cfg = {"configurable": {"thread_id": ctx.run_id}}
    await _invoke(agent, "pregunta", ctx, cfg)
    edited = {
        "type": "edit",
        "edited_action": {
            "name": "write_todos",
            "args": {"todos": [{"content": "plan editado", "status": "pending"}]},
        },
    }
    done = await _invoke(agent, "", ctx, cfg, resume=Command(resume={"decisions": [edited]}))
    assert done.value["todos"] == [{"content": "plan editado", "status": "pending"}]


async def test_writes_to_kb_are_denied_and_notes_are_stored_per_thread():
    store = InMemoryStore()
    model = ScriptedChatModel(
        script=[
            ai("", [("write_file", {"file_path": "/kb/nuevo.md", "content": "no"}, "w1")]),
            ai("", [("write_file", {"file_path": "/notes/conceptos.md", "content": "Definición"}, "w2")]),
            ai("hecho"),
        ]
    )
    agent = _agent("learn", model, store=store)
    ctx = _ctx("learn")
    messages = await _tool_messages(agent, "escribe", ctx, {"configurable": {"thread_id": ctx.run_id}})
    denied = [m for m in messages if m.name == "write_file" and "permission denied" in m.content]
    assert denied, [m.content for m in messages]
    notes = store.search((ctx.thread_id, "notes"))
    assert [item.key for item in notes] == ["/conceptos.md"]
    assert store.search(("kb",)) == []


async def test_reading_kb_registers_a_numbered_source_for_the_run():
    store = InMemoryStore()
    await _store_run_once(store, ("kb",), "/despliegue.md", DESPLIEGUE_DOC)
    model = ScriptedChatModel(
        script=[
            ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "r1")]),
            ai("Se despliega con el pipeline [1]."),
        ]
    )
    agent = _agent("learn", model, store=store)
    ctx = _ctx("learn")
    messages = await _tool_messages(agent, "cómo", ctx, {"configurable": {"thread_id": ctx.run_id}})
    reads = [m for m in messages if m.name == "read_file"]
    assert reads[0].content.startswith("Fuente [1]: despliegue")

    registry = get_registry(ctx.run_id)
    try:
        assert [(s.index, s.kind, s.ref) for s in registry.sources] == [(1, "kb", "/kb/despliegue.md")]
        _, citations, hallucinated = finalize("Se despliega con el pipeline [1].", registry)
        assert citations[0]["title"] == "despliegue" and hallucinated == 0
    finally:
        release_registry(ctx.run_id)


async def test_missing_kb_file_is_not_registered_as_source():
    model = ScriptedChatModel(
        script=[
            ai("", [("read_file", {"file_path": "/kb/no-existe.md"}, "r1")]),
            ai("No encontré nada."),
        ]
    )
    agent = _agent("learn", model)
    ctx = _ctx("learn")
    messages = await _tool_messages(agent, "busca", ctx, {"configurable": {"thread_id": ctx.run_id}})
    try:
        reads = [m.content for m in messages if m.name == "read_file"]
        assert len(reads) == 1 and reads[0].startswith("Error: File")
        assert not reads[0].startswith("Fuente [")
        assert get_registry(ctx.run_id).sources == []
    finally:
        release_registry(ctx.run_id)


async def test_subagent_shares_run_sources_and_usage_and_cannot_write_kb():
    store = InMemoryStore()
    await _store_run_once(store, ("kb",), "/despliegue.md", DESPLIEGUE_DOC)
    main = ScriptedChatModel(
        script=[
            ai("", [("task", {"description": "investiga el despliegue", "subagent_type": "investigador"}, "k1")]),
            ai("Informe con la fuente [1]."),
        ]
    )
    sub = ScriptedChatModel(
        script=[
            ai("", [("read_file", {"file_path": "/kb/despliegue.md"}, "s1")]),
            ai("", [("write_file", {"file_path": "/kb/intruso.md", "content": "no"}, "s2")]),
            ai("Resumen del subagente [1]."),
        ]
    )
    agent = _agent("research", main, subagent_model=sub, store=store)
    ctx = _ctx("research")
    cfg = {"configurable": {"thread_id": ctx.run_id}}
    usage = UsageMetadataCallbackHandler()
    messages = []
    async for part in agent.astream(
        {"messages": [{"role": "user", "content": "investiga"}]},
        cfg | {"callbacks": [usage]},
        context=ctx,
        stream_mode="updates",
        subgraphs=True,
        version="v2",
    ):
        if part["type"] == "updates":
            for update in part["data"].values():
                if isinstance(update, dict):
                    messages.extend(m for m in update.get("messages", []) or [] if isinstance(m, ToolMessage))
    try:
        assert any(m.name == "read_file" and m.content.startswith("Fuente [1]") for m in messages)
        assert any(m.name == "write_file" and "permission denied" in m.content for m in messages)
        assert [s.index for s in get_registry(ctx.run_id).sources] == [1]
        task_results = [m.content for m in messages if m.name == "task"]
        assert task_results and "Resumen del subagente [1]." in task_results[0]
        totals = usage.usage_metadata["scripted-test"]
        # 2 llamadas del agente principal y 3 del subagente, 10 tokens de entrada cada una.
        assert totals["input_tokens"] == 50
        assert totals["output_tokens"] == 25
    finally:
        release_registry(ctx.run_id)


async def test_explore_emits_directions_as_custom_stream_event():
    model = ScriptedChatModel(
        script=[
            ai(
                "Hay tres caminos.",
                [
                    (
                        "suggest_directions",
                        {"items": [{"title": "¿Qué es un canary?", "why": "Explica el despliegue gradual."}]},
                        "d1",
                    )
                ],
            ),
            ai("Elige una."),
        ]
    )
    agent = _agent("explore", model)
    ctx = _ctx("explore")
    payloads = []
    async for part in agent.astream(
        {"messages": [{"role": "user", "content": "explora"}]},
        {"configurable": {"thread_id": ctx.run_id}},
        context=ctx,
        stream_mode="custom",
        version="v2",
    ):
        if part["type"] == "custom":
            payloads.append(part["data"])
    assert payloads == [
        {
            "type": "ui.directions",
            "items": [{"title": "¿Qué es un canary?", "why": "Explica el despliegue gradual."}],
        }
    ]


async def test_failover_answers_from_fallback_when_primary_fails():
    fallback = ScriptedChatModel(script=[ai("Respuesta del respaldo.")])
    agent = _agent("learn", FailingChatModel(), fallbacks=[fallback])
    ctx = _ctx("learn")
    result = await _invoke(agent, "hola", ctx, {"configurable": {"thread_id": ctx.run_id}})
    assert result.value["messages"][-1].content.strip() == "Respuesta del respaldo."
