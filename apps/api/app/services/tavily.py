"""Cliente mínimo de la API de búsqueda de Tavily (HTTP, sin SDK).

La clave viaja solo en la cabecera `Authorization`. Los errores que salen de aquí no la contienen.
"""

from dataclasses import dataclass

import httpx

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_TIMEOUT_SECONDS = 15.0


class TavilyError(Exception):
    """La búsqueda no se pudo completar. El mensaje es legible y no incluye secretos."""


@dataclass(frozen=True)
class TavilyResult:
    title: str
    url: str
    content: str


async def tavily_search(api_key: str, query: str, *, max_results: int) -> list[TavilyResult]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"query": query, "max_results": max_results, "search_depth": "basic"},
            )
    except httpx.HTTPError as exc:
        raise TavilyError("No hubo conexión con Tavily") from exc

    if response.status_code in (401, 403):
        raise TavilyError("Tavily rechazó la clave")
    if response.status_code >= 400:
        raise TavilyError(f"Tavily respondió con el código {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise TavilyError("Tavily devolvió una respuesta que no es JSON") from exc

    results: list[TavilyResult] = []
    for item in payload.get("results") or []:
        url = str(item.get("url") or "")
        if not url:
            continue
        results.append(
            TavilyResult(
                title=str(item.get("title") or url),
                url=url,
                content=str(item.get("content") or ""),
            )
        )
    return results


__all__ = ["TAVILY_SEARCH_URL", "TavilyError", "TavilyResult", "tavily_search"]
