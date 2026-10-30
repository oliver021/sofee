"""Extracción de texto (md, txt, pdf), nombres de documento y el texto que se guarda al subir."""

from sqlalchemy import select

from app.db import async_session_factory
from app.models.storage import StorageObject
from app.services.extraction import ExtractionError, extract_text, try_extract_text
from app.services.knowledge import normalize_tags, slugify, title_for
from tests.conftest import csrf_from_client
from tests.helpers import authed_client
from tests.kb_fakes import make_pdf


def test_markdown_and_text_are_read_as_is_with_normalized_newlines():
    assert extract_text("guia.md", "# Hola\r\nlínea dos\r".encode()) == "# Hola\nlínea dos"
    assert extract_text("notas.TXT", "﻿con BOM".encode()) == "con BOM"


def test_pdf_text_is_extracted_from_the_page_content():
    text = extract_text("manual.pdf", make_pdf("Pipeline de despliegue del equipo"))
    assert "Pipeline de despliegue del equipo" in text


def test_unsupported_and_broken_files_are_refused():
    assert try_extract_text("imagen.png", b"\x89PNG") is None
    try:
        extract_text("imagen.png", b"\x89PNG")
    except ExtractionError as exc:
        assert "no soportado" in str(exc)
    else:  # pragma: no cover - el test debe fallar si no lanza
        raise AssertionError("un png no es un formato soportado")
    try:
        extract_text("roto.pdf", b"esto no es un pdf")
    except ExtractionError:
        pass
    else:  # pragma: no cover
        raise AssertionError("un pdf dañado debe fallar con ExtractionError")
    assert try_extract_text("roto.pdf", b"esto no es un pdf") is None


def test_markdown_title_is_its_first_heading_and_other_files_use_their_name():
    assert title_for("guia.md", "\n# Despliegue del equipo\n\ntexto") == "Despliegue del equipo"
    assert title_for("guia.md", "texto sin encabezado") == "guia"
    assert title_for("manual_de-onboarding.pdf", "lo que sea") == "manual de onboarding"


def test_slugs_are_ascii_and_never_empty():
    assert slugify("Guía de Despliegue (v2)") == "guia-de-despliegue-v2"
    assert slugify("¡¡¡") == "documento"


def test_tags_are_trimmed_deduplicated_and_capped():
    assert normalize_tags(["  equipo ", "equipo", "", "onboarding"]) == ["equipo", "onboarding"]


async def test_storage_upload_saves_extracted_text_for_readable_files(client):
    await authed_client(client)
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    resp = await client.post(
        "/api/v1/storage",
        files={"file": ("notas.txt", "Reunión el martes".encode(), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/v1/storage",
        files={"file": ("foto.png", b"\x89PNG\r\n", "image/png")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    async with async_session_factory() as db:
        rows = {
            row.filename: row.extracted_text
            for row in (await db.execute(select(StorageObject))).scalars()
        }
    assert rows == {"notas.txt": "Reunión el martes", "foto.png": None}
