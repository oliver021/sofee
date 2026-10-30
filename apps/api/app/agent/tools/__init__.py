"""Registro de herramientas del agente por nombre.

Los nombres que aparecen en un perfil se resuelven aquí. Las herramientas de búsqueda se crean
por run, con el límite de búsquedas del perfil; `web_search` solo se ofrece si hay una clave de
Tavily activa (`web_search=True`). Un nombre sin implementación se ignora sin error.
"""

from typing import Any

from langchain_core.tools import BaseTool

from .search import DEFAULT_MAX_SEARCHES, build_search_tools
from .ui import check_understanding, suggest_directions

_UI_TOOLS: tuple[BaseTool, ...] = (suggest_directions, check_understanding)


def get_tools(mode: str, profile_config: dict[str, Any], *, web_search: bool = False) -> list[BaseTool]:
    """Herramientas que necesita un perfil: las de `tools` y las de cada subagente.

    `mode` queda reservado para herramientas que solo existen en un modo concreto.
    `web_search` indica si hay clave de Tavily: sin ella, `web_search` no se ofrece al modelo.
    """
    del mode  # reservado: sin herramientas específicas de modo todavía
    limits = profile_config.get("limits") or {}
    max_searches = int(limits.get("max_searches", DEFAULT_MAX_SEARCHES))
    registry: dict[str, BaseTool] = {tool.name: tool for tool in _UI_TOOLS}
    for tool in build_search_tools(max_searches=max_searches, web_search=web_search):
        registry[tool.name] = tool

    names: list[str] = list(profile_config.get("tools", []))
    for subagent in profile_config.get("subagents", []):
        names.extend(subagent.get("tools", []))
    seen: set[str] = set()
    tools: list[BaseTool] = []
    for name in names:
        if name in seen or name not in registry:
            continue
        seen.add(name)
        tools.append(registry[name])
    return tools


__all__ = ["get_tools"]
