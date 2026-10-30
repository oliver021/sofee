import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ProviderKind(str, enum.Enum):
    vercel_gateway = "vercel_gateway"
    deepinfra = "deepinfra"
    nvidia_nim = "nvidia_nim"
    openai_compatible = "openai_compatible"


def _kind_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, name="provider_kind", values_callable=_kind_values)
    )
    base_url: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    default_headers: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    credentials: Mapped[list["ProviderCredential"]] = relationship(  # type: ignore[name-defined]
        back_populates="provider", cascade="all, delete-orphan"
    )
    models: Mapped[list["ProviderModel"]] = relationship(  # type: ignore[name-defined]
        back_populates="provider", cascade="all, delete-orphan"
    )


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    last_four: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provider: Mapped[Provider] = relationship(back_populates="credentials")


class ProviderModel(Base):
    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Aptitud para agentes (M-agente). `supports_tools` lo verifica una prueba real,
    # no se declara a mano; null = aún no probado.
    supports_tools: Mapped[bool | None] = mapped_column(Boolean)
    context_window: Mapped[int | None] = mapped_column(Integer)
    input_price_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    output_price_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provider: Mapped[Provider] = relationship(back_populates="models")