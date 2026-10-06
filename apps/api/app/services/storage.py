import os
import re
from pathlib import Path
import secrets
import uuid
from typing import Protocol

from ..config import settings


class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def presigned_url(self, key: str, expires_in: int) -> str | None: ...


class LocalDiskBackend:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        full = (self.root / key).resolve()
        if full != self.root and not str(full).startswith(str(self.root) + os.sep):
            raise ValueError("Invalid storage key")
        return full

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def presigned_url(self, key: str, expires_in: int) -> str | None:
        return None


_backend: StorageBackend | None = None


def build_storage_backend() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalDiskBackend(Path(settings.storage_local_dir))
    raise NotImplementedError(
        f"storage_backend={settings.storage_backend!r} no está implementado (solo 'local')"
    )


def get_storage_backend() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = build_storage_backend()
    return _backend


def generate_storage_key(filename: str) -> str:
    suffix = Path(filename).suffix
    safe_suffix = re.sub(r"[^A-Za-z0-9.]", "", suffix)[:32]
    return f"{uuid.uuid4().hex}{secrets.token_urlsafe(4)}{safe_suffix}"


__all__ = [
    "LocalDiskBackend",
    "StorageBackend",
    "build_storage_backend",
    "generate_storage_key",
    "get_storage_backend",
]