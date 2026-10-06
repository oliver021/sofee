"""Rate limiting para /auth/login — por IP y por email, sin Redis.

Usa la propia tabla `login_attempts`: cada intento (éxito o fallo) se registra y
el límite se computa contando fallos dentro de una ventana deslizante. La
limpieza de filas viejas es perezosa (se borran al hacer login), igual que la
poda de sesiones vencidas. Suficiente para frenar fuerza bruta; si el despliegue
es multi-nodo compartido, migrar a Redis es un cambio localizado en este módulo.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..config import settings
from ..models.login_attempt import LoginAttempt


def _failed_since(since: datetime) -> tuple[ColumnElement[bool], ...]:
    return (
        LoginAttempt.created_at >= since,
        LoginAttempt.success.is_(False),
    )


async def _dimension_retry_after(
    db: AsyncSession,
    column: ColumnElement,
    value: str | None,
    since: datetime,
    now: datetime,
) -> int:
    """Segundos hasta que una dimensión (email o IP) vuelve a estar bajo el límite."""
    if value is None:
        return 0
    max_attempts = settings.login_rate_limit_max_attempts
    rows = (
        (
            await db.execute(
                select(LoginAttempt.created_at)
                .where(column == value, *_failed_since(since))
                .order_by(LoginAttempt.created_at.asc())
                .limit(max_attempts)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < max_attempts:
        return 0
    release_at = rows[-1] + timedelta(seconds=settings.login_rate_limit_window_seconds)
    return max(1, min(int((release_at - now).total_seconds()), settings.login_rate_limit_window_seconds))


async def login_rate_limit_retry_after(
    db: AsyncSession, *, email: str, ip: str | None
) -> int | None:
    """Devuelve los segundos de espera si el intento está bloqueado, o None."""
    now = datetime.now(UTC)
    since = now - timedelta(seconds=settings.login_rate_limit_window_seconds)

    # Poda perezosa: filas fuera de la ventana ya no cuentan, se borran una vez por login.
    await db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < since))

    email_retry = await _dimension_retry_after(
        db, LoginAttempt.email, email.lower(), since, now
    )
    ip_retry = await _dimension_retry_after(
        db, LoginAttempt.ip_address, ip, since, now
    )
    retry = max(email_retry, ip_retry)
    return retry or None


def record_login_attempt(
    db: AsyncSession, *, email: str, ip: str | None, success: bool
) -> LoginAttempt:
    """Registra el intento (sin commitear; el commit lo cierra la ruta)."""
    attempt = LoginAttempt(email=email.lower(), ip_address=ip, success=success)
    db.add(attempt)
    return attempt