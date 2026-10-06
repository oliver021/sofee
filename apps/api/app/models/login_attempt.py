from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LoginAttempt(Base):
    """Intento de login (éxito o fallo) para rate limiting en /auth/login.

    Append-only en la práctica; se podan filas viejas de forma perezosa en cada
    login (misma estrategia lazy que las sesiones vencidas).
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, index=True)
    ip_address: Mapped[str | None] = mapped_column(Text, index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )