import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentProfile(Base):
    """Versión de perfil de agente por modo (learn, research, explore).

    Solo una fila por modo puede estar activa. Los defaults viven en código
    (`app/agent/profiles.py`); estas filas son las ediciones del admin.
    """

    __tablename__ = "agent_profiles"
    __table_args__ = (
        UniqueConstraint("mode", "version", name="uq_agent_profiles_mode_version"),
        Index(
            "uq_agent_profiles_active_mode",
            "mode",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    mode: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    system_prompt: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentRun(Base):
    """Un run del agente: una respuesta del asistente generada por el harness."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_thread_created", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("threads.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE")
    )
    user_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL")
    )
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    profile_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_profiles.id", ondelete="SET NULL")
    )
    catalog_slug: Mapped[str | None] = mapped_column(Text)
    provider_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("provider_models.id", ondelete="SET NULL")
    )
    model_label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    hallucinated_citations: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    trace_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRunEvent(Base):
    """Eventos del protocolo de Sofee de un run. Append-only; `seq` crece dentro del run."""

    __tablename__ = "agent_run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_agent_run_events_run_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
