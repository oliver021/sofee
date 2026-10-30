"""Base de conocimiento del equipo: nombres, rutas y búsqueda full-text sobre `kb_documents`.

`kb_documents` es la fuente de verdad del admin y de la búsqueda. La copia que ve el agente
(`/kb/`) la mantiene `app/agent/knowledge.py`.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.kb import KbDocument

KB_PREFIX = "/kb/"
MAX_TAGS = 20
MAX_TAG_LENGTH = 40
_TITLE_MAX = 200
_SLUG_MAX = 80
_SNIPPET_OPTIONS = 'MaxWords=30, MinWords=10, StartSel="", StopSel=""'

# Busca con las dos configuraciones: el tsvector tiene español e inglés (ver models/kb.py).
_SEARCH_SQL = text(
    """
    WITH query AS (
        SELECT websearch_to_tsquery('spanish', :q) || websearch_to_tsquery('english', :q) AS q
    )
    SELECT ranked.id, ranked.title, ts_headline('spanish', ranked.text, query.q, :options) AS snippet
    FROM (
        SELECT d.id, d.title, d.text, d.tsv
        FROM kb_documents d
        WHERE d.is_enabled AND d.tsv @@ (SELECT q FROM query)
    ) ranked, query
    ORDER BY ts_rank(ranked.tsv, query.q) DESC, ranked.title
    LIMIT :limit
    """
)


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    title: str
    snippet: str


@dataclass(frozen=True)
class EnabledDocument:
    document_id: str
    slug: str
    title: str


def kb_path(slug: str) -> str:
    """Ruta virtual que ve el agente: `/kb/<slug>.md`."""
    return f"{KB_PREFIX}{slug}.md"


def slugify(value: str) -> str:
    ascii_only = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug[:_SLUG_MAX].strip("-") or "documento"


def title_for(filename: str, text_content: str) -> str:
    """Título de un documento: su primer encabezado si es markdown; si no, el nombre del archivo."""
    if PurePosixPath(filename).suffix.lower() == ".md":
        for line in text_content.splitlines():
            stripped = line.strip()
            if stripped:
                if stripped.startswith("#"):
                    heading = stripped.lstrip("#").strip()
                    if heading:
                        return heading[:_TITLE_MAX]
                break
    stem = PurePosixPath(filename).stem
    humanized = re.sub(r"[-_]+", " ", stem).strip()
    return (humanized or filename)[:_TITLE_MAX]


def normalize_tags(tags: list[str]) -> list[str]:
    """Etiquetas sin espacios sobrantes ni duplicados, en el orden en que se escribieron."""
    result: list[str] = []
    for tag in tags:
        cleaned = tag.strip()[:MAX_TAG_LENGTH]
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result[:MAX_TAGS]


async def unique_slug(db: AsyncSession, base: str, reserved: set[str]) -> str:
    """Slug libre: `base`, o `base-2`, `base-3`... si ya existe o se reservó en esta subida."""
    candidate = base
    number = 2
    while candidate in reserved or await _slug_exists(db, candidate):
        candidate = f"{base}-{number}"
        number += 1
    reserved.add(candidate)
    return candidate


async def _slug_exists(db: AsyncSession, slug: str) -> bool:
    found = (
        await db.execute(select(KbDocument.id).where(KbDocument.slug == slug))
    ).first()
    return found is not None


async def enabled_documents(db: AsyncSession) -> list[EnabledDocument]:
    """Documentos activos sin su texto (el agente lo lee del store, no de aquí)."""
    rows = (
        await db.execute(
            select(KbDocument.id, KbDocument.slug, KbDocument.title)
            .where(KbDocument.is_enabled.is_(True))
            .order_by(KbDocument.slug)
        )
    ).all()
    return [
        EnabledDocument(document_id=str(row.id), slug=row.slug, title=row.title) for row in rows
    ]


async def search_documents(db: AsyncSession, query: str, *, limit: int) -> list[SearchHit]:
    """Documentos activos que casan con `query`, mejor puntuados primero, con un fragmento."""
    if not query.strip():
        return []
    rows = (
        await db.execute(
            _SEARCH_SQL,
            {"q": query, "options": _SNIPPET_OPTIONS, "limit": limit},
        )
    ).all()
    return [
        SearchHit(document_id=str(row.id), title=row.title, snippet=_one_line(row.snippet or ""))
        for row in rows
    ]


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


__all__ = [
    "KB_PREFIX",
    "MAX_TAGS",
    "MAX_TAG_LENGTH",
    "EnabledDocument",
    "SearchHit",
    "enabled_documents",
    "kb_path",
    "normalize_tags",
    "search_documents",
    "slugify",
    "title_for",
    "unique_slug",
]
