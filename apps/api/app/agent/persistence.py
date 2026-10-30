"""Checkpointer y store de LangGraph sobre Postgres (psycopg 3, no asyncpg).

El pool de psycopg se abre en el lifespan de FastAPI y se cierra al salir. Las
tablas del checkpointer y del store las crea el paso `migrate` del release
(`python -m app.cli setup-agent-storage`), nunca el arranque de la API.
Con `TESTING=true` se usan las versiones en memoria.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from ..config import settings


@dataclass
class AgentStorage:
    checkpointer: BaseCheckpointSaver
    store: BaseStore
    pool: AsyncConnectionPool | None


_current: AgentStorage | None = None


def psycopg_conninfo(database_url: str | None = None) -> str:
    """`postgresql+asyncpg://...` -> `postgresql://...` (lo que entiende psycopg)."""
    url = make_url(database_url or settings.database_url)
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _open_pool(database_url: str | None = None) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        conninfo=psycopg_conninfo(database_url),
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        open=False,
    )


async def open_agent_storage() -> AgentStorage:
    """Crea el checkpointer y el store (en memoria si `TESTING`, Postgres si no)."""
    global _current
    if settings.testing:
        _current = AgentStorage(checkpointer=InMemorySaver(), store=InMemoryStore(), pool=None)
        return _current
    pool = _open_pool()
    await pool.open(wait=True)
    _current = AgentStorage(
        checkpointer=AsyncPostgresSaver(pool),
        store=AsyncPostgresStore(pool),
        pool=pool,
    )
    return _current


async def close_agent_storage(storage: AgentStorage) -> None:
    global _current
    if storage.pool is not None:
        await storage.pool.close()
    if _current is storage:
        _current = None


@asynccontextmanager
async def agent_storage_lifespan(app: FastAPI) -> AsyncIterator[None]:
    storage = await open_agent_storage()
    app.state.agent_storage = storage
    try:
        yield
    finally:
        await close_agent_storage(storage)


def get_agent_storage() -> AgentStorage:
    """El almacenamiento abierto por el lifespan; en tests, uno en memoria bajo demanda."""
    global _current
    if _current is None:
        if not settings.testing:
            raise RuntimeError("Agent storage is not open (lifespan not started)")
        _current = AgentStorage(checkpointer=InMemorySaver(), store=InMemoryStore(), pool=None)
    return _current


def reset_in_memory_storage() -> None:
    """Solo tests (`TESTING`): descarta el checkpointer y el store en memoria para que un test no
    herede los archivos de /kb/ o los checkpoints de otro."""
    global _current
    if not settings.testing:
        raise RuntimeError("reset_in_memory_storage solo se usa con TESTING=true")
    _current = None


async def setup_agent_storage(database_url: str | None = None) -> None:
    """Crea las tablas del checkpointer y del store. Idempotente. Lo llama la CLI del release."""
    pool = _open_pool(database_url)
    await pool.open(wait=True)
    try:
        await AsyncPostgresSaver(pool).setup()
        await AsyncPostgresStore(pool).setup()
    finally:
        await pool.close()
