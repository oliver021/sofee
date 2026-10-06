import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ModelCatalogEntry(Base):
    __tablename__ = "model_catalog_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    slug: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    bindings: Mapped[list["ModelCatalogBinding"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="ModelCatalogBinding.priority"
    )


class ModelCatalogBinding(Base):
    __tablename__ = "model_catalog_bindings"
    __table_args__ = (
        UniqueConstraint("catalog_entry_id", "provider_model_id", name="uq_catalog_binding"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    catalog_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("model_catalog_entries.id", ondelete="CASCADE"), index=True
    )
    provider_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("provider_models.id", ondelete="CASCADE"), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    entry: Mapped[ModelCatalogEntry] = relationship(back_populates="bindings")
    provider_model: Mapped["ProviderModel"] = relationship()  # type: ignore[name-defined]
