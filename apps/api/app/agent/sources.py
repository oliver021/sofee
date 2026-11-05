"""Registro de fuentes por run y la numeración global `[n]` de las citas.

El registro se indexa por `run_id`, no por agente: el agente principal y los
subagentes comparten la numeración. `SourcesMiddleware` registra cada documento
que el agente lee de `/kb/` o `/attachments/`; las herramientas de búsqueda (B2)
registran sus resultados web con el mismo `SourceRegistry.add`.
"""

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

SourceKind = Literal["web", "kb", "attachment"]

# Respeta el orden de aparición: las citas se numeran 1..k según cómo se ven en el texto.
# Los bloques de código no se tocan (por ejemplo, `arr[1]` no es una cita).
_CITATION_RE = re.compile(r"(```.*?```|`[^`\n]*`)|\[(\d+)\]", re.DOTALL)


@dataclass(frozen=True)
class Source:
    index: int
    kind: SourceKind
    title: str
    url: str | None
    snippet: str | None
    ref: str | None


@dataclass(frozen=True)
class DocumentRef:
    """Documento al que apunta una ruta virtual de `/kb/` o `/attachments/` en este run.

    `ref` es el id de `kb_documents` o de `storage_objects`, que es lo que la UI abre.
    """

    ref: str
    title: str


class SourceRegistry:
    """Fuentes de un run. `index` es la numeración global del run (empieza en 1)."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._sources: list[Source] = []
        self._by_key: dict[tuple[str, str], int] = {}
        # Ruta virtual -> documento, preparado al empezar el run (ver app/agent/knowledge.py).
        self.documents: dict[str, DocumentRef] = {}
        # Presupuesto del run: intentos de búsqueda y de subagentes. Cuentan también tras reanudar.
        self.searches = 0
        # Pasajes recuperados antes de responder (ver grounding.py); `None` = aún no se intentó.
        self.grounding: str | None = None
        self.subagents = 0

    @property
    def sources(self) -> list[Source]:
        return list(self._sources)

    def get(self, index: int) -> Source | None:
        if 1 <= index <= len(self._sources):
            return self._sources[index - 1]
        return None

    def add(
        self,
        *,
        kind: SourceKind,
        title: str,
        url: str | None = None,
        snippet: str | None = None,
        ref: str | None = None,
    ) -> int:
        """Registra una fuente y devuelve su índice. Repetir la misma fuente devuelve el mismo índice."""
        key = (kind, ref or url or title)
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        source = Source(
            index=len(self._sources) + 1,
            kind=kind,
            title=title,
            url=url,
            snippet=snippet,
            ref=ref,
        )
        self._sources.append(source)
        self._by_key[key] = source.index
        _emit_source_added(source)
        return source.index


def _emit_source_added(source: Source) -> None:
    """Emite `source.added` por el stream custom. Fuera de un grafo no hace nada."""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(
        {
            "type": "source.added",
            "index": source.index,
            "title": source.title,
            "url": source.url,
            "kind": source.kind,
            "ref": source.ref,
        }
    )


# Un registro por run; el executor lo libera al terminar el run (`release_registry`).
_registries: dict[str, SourceRegistry] = {}


def get_registry(run_id: str) -> SourceRegistry:
    registry = _registries.get(run_id)
    if registry is None:
        registry = SourceRegistry(run_id)
        _registries[run_id] = registry
    return registry


def release_registry(run_id: str) -> None:
    _registries.pop(run_id, None)


def finalize(text: str, registry: SourceRegistry) -> tuple[str, list[dict[str, Any]], int]:
    """Renumera las citas del texto final y devuelve las fuentes citadas.

    Devuelve `(texto, citas, citas_alucinadas)`:
    - cada `[n]` que existe en el registro pasa a `[k]`, con k en orden de aparición;
    - un `[n]` que no existe en el registro se elimina y cuenta como alucinado;
    - las citas son `{index, title, url, kind, snippet, ref}`, solo de las fuentes usadas.
    """
    numbering: dict[int, int] = {}
    citations: list[dict[str, Any]] = []
    hallucinated = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal hallucinated
        if match.group(1) is not None:
            return match.group(0)
        old = int(match.group(2))
        source = registry.get(old)
        if source is None:
            hallucinated += 1
            return ""
        if old not in numbering:
            numbering[old] = len(numbering) + 1
            citations.append(
                {
                    "index": numbering[old],
                    "title": source.title,
                    "url": source.url,
                    "kind": source.kind,
                    "snippet": source.snippet,
                    "ref": source.ref,
                }
            )
        return f"[{numbering[old]}]"

    renumbered = _CITATION_RE.sub(replace, text)
    return renumbered, citations, hallucinated


# Rutas cuyas lecturas (`read_file`) cuentan como fuente.
_SOURCE_ROUTES: dict[str, SourceKind] = {
    "/kb/": "kb",
    "/attachments/": "attachment",
}


def _source_kind_for(path: str) -> SourceKind | None:
    for prefix, kind in _SOURCE_ROUTES.items():
        if path.startswith(prefix):
            return kind
    return None


def _title_for(path: str) -> str:
    stem = os.path.splitext(PurePosixPath(path).name)[0]
    return stem.replace("-", " ").replace("_", " ").strip() or path


class SourcesMiddleware(AgentMiddleware):
    """Registra como fuente cada lectura de `/kb/` o `/attachments/` y la marca en el resultado.

    Va en el agente principal y en cada subagente: el middleware no se hereda.
    """

    def wrap_tool_call(self, request: ToolCallRequest, handler):  # noqa: ANN001, ANN201
        result = handler(request)
        return self._annotate(request, result)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):  # noqa: ANN001, ANN201
        result = await handler(request)
        return self._annotate(request, result)

    def _annotate(
        self, request: ToolCallRequest, result: ToolMessage | Command
    ) -> ToolMessage | Command:
        if request.tool_call["name"] != "read_file" or not isinstance(result, ToolMessage):
            return result
        # Un archivo que no existe no es fuente: el resultado es un texto "Error: ...", no un status.
        if result.status == "error" or not isinstance(result.content, str):
            return result
        if result.content.startswith("Error"):
            return result
        path = str(request.tool_call["args"].get("file_path", ""))
        kind = _source_kind_for(path)
        if kind is None:
            return result

        registry = get_registry(request.runtime.context.run_id)
        known = registry.documents.get(path)
        title = known.title if known is not None else _title_for(path)
        ref = known.ref if known is not None else path
        index = registry.add(kind=kind, title=title, ref=ref)
        return result.model_copy(update={"content": f"Fuente [{index}]: {title}\n{result.content}"})


def strip_citation_markers(text: str) -> str:
    """Quita los `[n]` de un texto, salvo dentro de bloques de código.

    Las citas se numeran por run: un `[1]` de una respuesta antigua no apunta a nada en el run
    actual, y el modelo lo copia. Solo se usa para armar el historial, no para lo guardado.
    """
    cleaned = _CITATION_RE.sub(lambda match: match.group(1) or "", text)
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)


__all__ = [
    "DocumentRef",
    "Source",
    "SourceRegistry",
    "strip_citation_markers",
    "SourcesMiddleware",
    "finalize",
    "get_registry",
    "release_registry",
]
