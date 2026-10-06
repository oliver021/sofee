from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


class CryptoError(Exception):
    pass


_DEV_TEST_KEY = "ueGCNHuIEzqC74xaTvS6Hwcphg0hbEHc3GtNICty7_o="


def get_fernet() -> Fernet:
    key = settings.secret_encryption_key or (_DEV_TEST_KEY if settings.testing else None)
    if not key:
        raise CryptoError(
            "SECRET_ENCRYPTION_KEY is required to encrypt provider credentials"
        )
    return Fernet(key.encode())


def encrypt_secret(secret: str, fernet: Fernet | None = None) -> bytes:
    return (fernet or get_fernet()).encrypt(secret.encode())


def decrypt_secret(ciphertext: bytes, fernet: Fernet | None = None) -> str:
    try:
        return (fernet or get_fernet()).decrypt(ciphertext).decode()
    except InvalidToken:
        raise CryptoError("Could not decrypt credential (invalid key?)")


def last_four(secret: str) -> str:
    return secret[-4:] if len(secret) >= 4 else secret