import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# El tsvector cubre español e inglés a la vez: el stemming de cualquiera de los dos encuentra el
# documento. Lo mantiene Postgres (columna generada), así que nunca se escribe a mano.
KB_TSV_EXPRESSION = (
    "setweight(to_tsvector('spanish', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "to_tsvector('spanish', coalesce(text, '')) || "
    "to_tsvector('english', coalesce(text, ''))"
)


class KbDocument(Base):
    """Documento de la base de conocimiento del equipo. `text` es lo que el agente lee."""

    __tablename__ = "kb_documents"
    __table_args__ = (Index("ix_kb_documents_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=sa_text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    # Ruta virtual que ve el agente: /kb/<slug>.md (la copia en el store usa /<slug>.md).
    path: Mapped[str] = mapped_column(Text)
    source_filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, server_default=sa_text("''"))
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(KB_TSV_EXPRESSION, persisted=True), nullable=True
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=sa_text("'{}'"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("true"))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KbChunk(Base):
    """Trozo de un documento con su embedding. Es lo que recupera el RAG.

    Se borra con su documento. `embedding` es un `float[]` normalizado (norma 1), así que el
    producto punto es el coseno. `model` guarda con qué modelo se calculó: un trozo de otro
    modelo no se compara con la consulta (los espacios vectoriales no son compatibles).
    """

    __tablename__ = "kb_chunks"
    __table_args__ = (Index("ix_kb_chunks_document_id", "document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("kb_documents.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(Text, server_default=sa_text("''"))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float))
    model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
