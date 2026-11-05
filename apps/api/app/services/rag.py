"""RAG sobre la base de conocimiento: indexa trozos con embeddings y recupera pasajes.

La recuperación es híbrida. Ordena los trozos por similitud coseno con la consulta y suma, con
una pesada menor, la posición de su documento en la búsqueda full-text (fusión por rango, RRF).
Así una consulta con las palabras exactas ("SEV1") y otra parafraseada encuentran lo mismo.

El producto punto se calcula en Python sobre los trozos activos: para una base de conocimiento
de equipo (cientos o pocos miles de trozos) basta y no pide la extensión pgvector. Si la base
crece, `retrieve` es el único sitio que cambia.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.kb import KbChunk, KbDocument
from .chunking import chunk_text
from .embeddings import EmbeddingsError, current_model, embed_texts, embeddings_enabled
from .knowledge import search_documents

logger = logging.getLogger(__name__)

RRF_K = 60
LEXICAL_WEIGHT = 0.25
MAX_CHUNKS_PER_DOCUMENT = 2
_LEXICAL_POOL = 20
# Una consulta de pocas palabras casa con casi cualquier cosa: se le exige más parecido.
_SHORT_QUERY_WORDS = 4
_SHORT_QUERY_EXTRA_SIMILARITY = 0.07
_TITLE_QUERY_MAX_WORDS = 3


@dataclass(frozen=True)
class RagHit:
    document_id: str
    title: str
    heading: str
    text: str
    score: float


async def index_document(db: AsyncSession, document: KbDocument) -> int:
    """Reemplaza los trozos del documento. Devuelve cuántos guardó (0 si no hay embeddings)."""
    model = current_model()
    if model is None:
        return 0
    chunks = chunk_text(
        document.text,
        max_chars=settings.rag_chunk_chars,
        overlap_chars=settings.rag_chunk_overlap_chars,
    )
    # Se calculan antes de borrar: si el servicio falla, el documento conserva su índice anterior.
    vectors = await embed_texts([_embedding_input(document.title, c.heading, c.text) for c in chunks])
    await db.execute(delete(KbChunk).where(KbChunk.document_id == document.id))
    for chunk, vector in zip(chunks, vectors, strict=True):
        db.add(
            KbChunk(
                document_id=document.id,
                position=chunk.position,
                heading=chunk.heading,
                text=chunk.text,
                embedding=vector,
                model=model,
            )
        )
    await db.flush()
    return len(chunks)


async def index_document_safely(db: AsyncSession, document: KbDocument) -> int:
    """Como `index_document`, pero un fallo del servicio de embeddings no rompe la subida:
    el documento queda buscable por full-text y `reindex-kb` lo indexa después."""
    try:
        return await index_document(db, document)
    except EmbeddingsError:
        logger.warning("No se pudo indexar %s; queda solo con full-text", document.slug)
        return 0


async def reindex_all(db: AsyncSession) -> tuple[int, int]:
    """Reindexa todos los documentos. Devuelve (documentos, trozos)."""
    documents = (await db.execute(select(KbDocument).order_by(KbDocument.slug))).scalars().all()
    total = 0
    for document in documents:
        total += await index_document(db, document)
    return len(documents), total


async def retrieve(db: AsyncSession, query: str, *, limit: int) -> list[RagHit] | None:
    """Pasajes más relevantes para `query`. `None` si el RAG no está disponible (sin embeddings
    configurados, servicio caído o nada indexado con el modelo actual): el llamador cae a full-text.
    Lista vacía si la base de conocimiento no responde a la pregunta: el mejor trozo no llega a
    `rag_min_similarity`. Las coincidencias de palabras solo reordenan, nunca rescatan un trozo."""
    model = current_model()
    if model is None or not query.strip():
        return None
    rows = (
        await db.execute(
            select(KbChunk, KbDocument.title)
            .join(KbDocument, KbDocument.id == KbChunk.document_id)
            .where(KbDocument.is_enabled.is_(True), KbChunk.model == model)
        )
    ).all()
    if not rows:
        return None
    try:
        [query_vector] = await embed_texts([_query_input(query)])
    except EmbeddingsError:
        logger.warning("Embeddings no disponibles al buscar; se usa full-text")
        return None

    lexical = await search_documents(db, query, limit=_LEXICAL_POOL)
    lexical_rank = {hit.document_id: rank for rank, hit in enumerate(lexical, start=1)}

    scored = sorted(
        ((_dot(query_vector, chunk.embedding), chunk, title) for chunk, title in rows),
        key=lambda item: item[0],
        reverse=True,
    )
    required = settings.rag_min_similarity
    if len(query.split()) < _SHORT_QUERY_WORDS:
        required += _SHORT_QUERY_EXTRA_SIMILARITY
    if not scored or scored[0][0] < required:
        # Salvo una búsqueda por título ("glosario"): ahí se devuelven los trozos de ese documento.
        titled = _documents_titled(query, [(chunk, title) for _, chunk, title in scored])
        scored = [item for item in scored if str(item[1].document_id) in titled]
        if not scored:
            return []
    floor = scored[0][0] - settings.rag_similarity_margin
    fused: list[tuple[float, float, KbChunk, str]] = []
    for vector_rank, (similarity, chunk, title) in enumerate(scored, start=1):
        score = 1 / (RRF_K + vector_rank)
        doc_rank = lexical_rank.get(str(chunk.document_id))
        if doc_rank is not None:
            score += LEXICAL_WEIGHT / (RRF_K + doc_rank)
        fused.append((score, similarity, chunk, title))
    fused.sort(key=lambda item: item[0], reverse=True)

    hits: list[RagHit] = []
    per_document: dict[str, int] = {}
    for score, similarity, chunk, title in fused:
        key = str(chunk.document_id)
        if similarity < floor:
            continue
        if per_document.get(key, 0) >= MAX_CHUNKS_PER_DOCUMENT:
            continue
        per_document[key] = per_document.get(key, 0) + 1
        hits.append(RagHit(key, title, chunk.heading, chunk.text, round(score, 6)))
        if len(hits) >= limit:
            break
    return hits


def _documents_titled(query: str, rows: list[tuple[KbChunk, str]]) -> set[str]:
    """Documentos cuyo título contiene toda la consulta, si esta es corta (hasta 3 palabras)."""
    needle = query.casefold().strip()
    if not needle or len(needle.split()) > _TITLE_QUERY_MAX_WORDS:
        return set()
    return {str(chunk.document_id) for chunk, title in rows if needle in title.casefold()}


def _embedding_input(title: str, heading: str, text: str) -> str:
    """Lo que se embebe lleva título y encabezado: un pasaje suelto sigue diciendo de qué trata."""
    context = " › ".join(part for part in (title, heading) if part)
    return f"{context}\n\n{text}" if context else text


def _query_input(query: str) -> str:
    # En un .env el salto de línea del prefijo llega como los dos caracteres `\n`.
    return settings.embeddings_query_prefix.replace("\\n", "\n") + query


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


__all__ = [
    "RagHit",
    "embeddings_enabled",
    "index_document",
    "index_document_safely",
    "reindex_all",
    "retrieve",
]
