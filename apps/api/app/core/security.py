from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


class PasswordError(Exception):
    pass


_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_is_valid(password: str, email: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if password.lower() == email.lower():
        return "Password must not be the same as the email"
    return None