"""Herramientas de búsqueda: documentos del equipo (RAG con respaldo en Postgres FTS) y la web (Tavily).

Cada resultado se registra en las fuentes del run y vuelve ya numerado `[n]`, así que el modelo
solo puede citar números que existen. Todas cuentan contra `max_searches` del perfil.
"""

from urllib.parse import urlsplit

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

from ...db import async_session_factory
from ...services.integrations import TAVILY, active_secret
from ...services.knowledge import search_documents
from ...services.rag import retrieve
from ...services.tavily import TavilyError, tavily_search
from ..context import SofeeContext
from ..sources import get_registry

# Parametrizado con el contexto: sin el parámetro, pydantic avisa al serializar la llamada.
ToolCtx = ToolRuntime[SofeeContext, dict]

DEFAULT_MAX_SEARCHES = 6
SEARCH_TOOL_NAMES = frozenset({"search_team_docs", "web_search"})
_MAX_RESULTS_CAP = 10
_QUERY_CAP = 300
_SNIPPET_CHARS = 300


def build_search_tools(*, max_searches: int, web_search: bool) -> list[BaseTool]:
    """Herramientas de búsqueda con el límite del perfil. `web_search` solo si hay clave de Tavily."""

    def claim(runtime: ToolCtx) -> str | None:
        """Cuenta un intento. Devuelve el mensaje de rechazo si el run ya agotó sus búsquedas."""
        registry = get_registry(runtime.context.run_id)
        already = registry.searches
        registry.searches += 1
        if already >= max_searches:
            return (
                f"Error: se alcanzó el límite de {max_searches} búsquedas para este run. "
                "Responde con lo que ya tienes y di lo que no pudiste verificar."
            )
        return None

    @tool
    async def search_team_docs(query: str, runtime: ToolCtx, limit: int = 5) -> str:
        """Busca en la documentación del equipo. Devuelve pasajes numerados como
        [n] Título › Sección — pasaje. Responde solo con lo que digan esos pasajes y cítalos con su
        número; si no cubren la pregunta, dilo. Para leer un documento completo, usa read_file con
        su ruta en /kb/."""
        refused = claim(runtime)
        if refused is not None:
            return refused
        runtime.stream_writer({"type": "status", "text": "Buscando en la documentación del equipo", "key": "searching_docs"})
        wanted = _clamp(limit, 5)
        async with async_session_factory() as db:
            passages = await retrieve(db, query[:_QUERY_CAP], limit=wanted)
            hits = [] if passages is not None else await search_documents(db, query[:_QUERY_CAP], limit=wanted)
        registry = get_registry(runtime.context.run_id)
        lines = []
        if passages is not None:
            for passage in passages:
                label = f"{passage.title} › {passage.heading}" if passage.heading else passage.title
                index = registry.add(
                    kind="kb", title=passage.title, ref=passage.document_id, snippet=_clip(passage.text)
                )
                lines.append(f"[{index}] {label} — {passage.text}")
        else:
            for hit in hits:
                index = registry.add(kind="kb", title=hit.title, ref=hit.document_id, snippet=hit.snippet)
                lines.append(f"[{index}] {hit.title} — {hit.snippet}")
        if not lines:
            return "No hay documentos del equipo que coincidan con la búsqueda."
        return "\n".join(lines)

    tools: list[BaseTool] = [search_team_docs]
    if not web_search:
        return tools

    @tool
    async def web_search(query: str, runtime: ToolCtx, max_results: int = 5) -> str:
        """Busca en la web. Devuelve resultados numerados como [n] Título — dominio, con un fragmento
        debajo. Úsalo solo cuando la documentación del equipo no cubra el tema."""
        refused = claim(runtime)
        if refused is not None:
            return refused
        runtime.stream_writer({"type": "status", "text": "Buscando en la web", "key": "searching_web"})
        async with async_session_factory() as db:
            api_key = await active_secret(db, TAVILY)
        if api_key is None:
            return "La búsqueda web no está configurada."
        try:
            results = await tavily_search(
                api_key, query[:_QUERY_CAP], max_results=_clamp(max_results, 5)
            )
        except TavilyError as exc:
            return f"Error: la búsqueda web falló ({exc})."
        if not results:
            return "La búsqueda web no devolvió resultados."
        registry = get_registry(runtime.context.run_id)
        lines = []
        for result in results:
            snippet = _clip(result.content)
            index = registry.add(kind="web", title=result.title, url=result.url, snippet=snippet)
            lines.append(f"[{index}] {result.title} — {urlsplit(result.url).netloc or result.url}\n{snippet}")
        return "\n".join(lines)

    tools.append(web_search)
    return tools


def _clamp(value: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, _MAX_RESULTS_CAP))


def _clip(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= _SNIPPET_CHARS else cleaned[: _SNIPPET_CHARS - 1] + "…"


__all__ = ["DEFAULT_MAX_SEARCHES", "SEARCH_TOOL_NAMES", "build_search_tools"]
