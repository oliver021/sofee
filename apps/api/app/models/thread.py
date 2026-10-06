import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    JSON,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (UniqueConstraint("owner_id", "client_id", name="uq_threads_owner_client"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=sa_text("gen_random_uuid()")
    )
    # `client_id` es el id local de apps/web; todos los endpoints de conversación
    # direccionan threads por él para que el frontend nunca tenga que remapear ids.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text, server_default=sa_text("'learn'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "client_id", name="uq_messages_thread_client"),
        Index("ix_messages_thread_seq", "thread_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=sa_text("gen_random_uuid()")
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=sa_text("'complete'"))
    citations: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attachment_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    thread: Mapped[Thread] = relationship(back_populates="messages")