"""Extracción de texto de los archivos subidos: adjuntos del hilo y base de conocimiento.

Se hace al subir, nunca al leer: el agente no espera a un parser (roadmap §3.5). Formatos:
md y txt tal cual, y pdf con pypdf. Cualquier otro formato se rechaza.
"""

import io
from pathlib import PurePosixPath

from pypdf import PasswordType, PdfReader

TEXT_EXTENSIONS = frozenset({".md", ".txt"})
PDF_EXTENSION = ".pdf"
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {PDF_EXTENSION}

CONTENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


class ExtractionError(Exception):
    """El archivo no se puede leer: formato no soportado, dañado o protegido con contraseña."""


def extension_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def extract_text(filename: str, data: bytes) -> str:
    """Texto plano del archivo. Puede ser vacío (un PDF escaneado no tiene capa de texto)."""
    suffix = extension_of(filename)
    if suffix in TEXT_EXTENSIONS:
        return _normalize(data.decode("utf-8-sig", errors="replace"))
    if suffix == PDF_EXTENSION:
        return _extract_pdf(data)
    raise ExtractionError(f"Formato no soportado: {suffix or 'sin extensión'}")


def try_extract_text(filename: str, data: bytes) -> str | None:
    """Como `extract_text`, pero `None` si el formato no se soporta o el archivo no se puede leer."""
    try:
        return extract_text(filename, data)
    except ExtractionError:
        return None


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            raise ExtractionError("El PDF tiene contraseña")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf lanza tipos distintos según cómo esté dañado el archivo
        raise ExtractionError("No se pudo leer el PDF") from exc
    return _normalize("\n\n".join(pages))


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


__all__ = [
    "CONTENT_TYPES",
    "ExtractionError",
    "SUPPORTED_EXTENSIONS",
    "extension_of",
    "extract_text",
    "try_extract_text",
]
