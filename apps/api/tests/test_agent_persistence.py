import uuid
from copy import deepcopy

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from app.agent.backends import make_backend
from app.agent.context import SofeeContext
from app.agent.models import ResolvedModel
from app.agent.persistence import (
    _open_pool,
    close_agent_storage,
    get_agent_storage,
    open_agent_storage,
    psycopg_conninfo,
    setup_agent_storage,
)
from app.agent.profiles import DEFAULT_PROFILES, ProfileSpec, build_agent
from app.agent.tools import get_tools
from tests.agent_fakes import ScriptedChatModel, ai


def test_psycopg_conninfo_drops_the_sqlalchemy_driver():
    assert psycopg_conninfo("postgresql+asyncpg://u:p%40s@db:5432/sofee") == "postgresql://u:p%40s@db:5432/sofee"


async def test_storage_is_in_memory_under_testing():
    storage = await open_agent_storage()
    try:
        assert isinstance(storage.checkpointer, InMemorySaver)
        assert isinstance(storage.store, InMemoryStore)
        assert storage.pool is None
        assert get_agent_storage() is storage
    finally:
        await close_agent_storage(storage)


async def test_setup_agent_storage_creates_tables_and_is_idempotent():
    await setup_agent_storage()
    await setup_agent_storage()


async def test_plan_review_resumes_on_postgres_with_a_new_saver():
    """Un run interrumpido sigue reanudable aunque cambie el objeto checkpointer (reinicio)."""
    model = ScriptedChatModel(
        script=[
            ai("", [("write_todos", {"todos": [{"content": "buscar", "status": "pending"}]}, "t1")]),
            ai("Plan aprobado, informe listo."),
        ]
    )
    defaults = DEFAULT_PROFILES["research"]

    def agent_with(saver, store):
        resolved = ResolvedModel(
            chat_model=model,
            label="Prueba",
            catalog_slug="prueba",
            provider_model_id=uuid.uuid4(),
            context_window=None,
            input_price=None,
            output_price=None,
        )
        profile = ProfileSpec(mode="research", system_prompt=defaults["system_prompt"], config=deepcopy(defaults["config"]))
        return build_agent(profile, resolved, get_tools("research", profile.config), make_backend(), saver, store)

    ctx = SofeeContext(user_id="u", thread_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()), mode="research", locale="es")
    cfg = {"configurable": {"thread_id": ctx.run_id}}
    pool = _open_pool()
    await pool.open(wait=True)
    try:
        store = AsyncPostgresStore(pool)
        await store.setup()
        first = agent_with(AsyncPostgresSaver(pool), store)
        paused = await first.ainvoke({"messages": [{"role": "user", "content": "pregunta"}]}, cfg, context=ctx, version="v2")
        assert len(paused.interrupts) == 1

        second = agent_with(AsyncPostgresSaver(pool), store)
        done = await second.ainvoke(
            Command(resume={"decisions": [{"type": "approve"}]}), cfg, context=ctx, version="v2"
        )
        assert done.interrupts == ()
        assert done.value["messages"][-1].content == "Plan aprobado, informe listo."
    finally:
        async with pool.connection() as conn:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (ctx.run_id,))
        await pool.close()
