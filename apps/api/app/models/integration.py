import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, LargeBinary, Text, Uuid, func
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class IntegrationCredential(Base):
    """Clave de una integración externa (hoy: Tavily). Cifrada igual que las de los providers.

    Solo una fila activa por `kind`. Las claves antiguas se conservan inactivas, para auditoría.
    """

    __tablename__ = "integration_credentials"
    __table_args__ = (
        Index(
            "uq_integration_credentials_active_kind",
            "kind",
            unique=True,
            postgresql_where=sa_text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=sa_text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text)
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    last_four: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sa_text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
