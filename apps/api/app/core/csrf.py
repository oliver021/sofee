import hashlib
import hmac
import uuid

from ..config import settings

_PREFIX = b"csrf:"


def derive_csrf_token(session_id: uuid.UUID) -> str:
    message = _PREFIX + session_id.bytes
    return hmac.new(settings.csrf_secret.encode(), message, hashlib.sha256).hexdigest()


def verify_csrf_token(session_id: uuid.UUID, token: str | None) -> bool:
    if not token:
        return False
    expected = derive_csrf_token(session_id)
    return hmac.compare_digest(token, expected)