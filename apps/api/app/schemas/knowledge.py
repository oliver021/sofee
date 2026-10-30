import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from ..services.knowledge import MAX_TAGS


class KbDocumentOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    path: str
    source_filename: str
    content_type: str
    size_bytes: int
    tags: list[str]
    is_enabled: bool
    # Longitud del texto extraído: 0 significa que el archivo no tenía texto (un PDF escaneado).
    text_chars: int
    created_at: datetime
    updated_at: datetime


class KbDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=MAX_TAGS)
    is_enabled: bool | None = None


class KbRejectedFile(BaseModel):
    filename: str
    # Código, no texto: `unsupported_type`, `too_large`, `extraction_failed`. El admin lo traduce.
    reason: str


class KbUploadOut(BaseModel):
    documents: list[KbDocumentOut]
    rejected: list[KbRejectedFile]


class KbTextOut(BaseModel):
    id: uuid.UUID
    title: str
    text: str
    text_chars: int
    truncated: bool


__all__ = [
    "KbDocumentOut",
    "KbDocumentUpdate",
    "KbRejectedFile",
    "KbTextOut",
    "KbUploadOut",
]
