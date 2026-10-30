"""Búsqueda full-text sobre la base de conocimiento: español e inglés, solo activos, con fragmento."""

from app.db import async_session_factory
from app.models.kb import KbDocument
from app.services.knowledge import search_documents
from tests.conftest import csrf_from_client
from tests.helpers import authed_client
from tests.kb_fakes import make_pdf


async def _add(client, name: str, body: bytes) -> str:
    resp = await client.post(
        "/api/v1/admin/kb",
        files=[("files", (name, body, "text/markdown"))],
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["documents"][0]["id"]


async def test_search_finds_spanish_and_english_text_and_returns_snippets(client):
    await authed_client(client)
    await _add(client, "bases.md", "# Bases de datos\n\nLa base de datos del equipo es Postgres.".encode())
    await _add(client, "deploy.md", "# Deployment\n\nThe nightly deployment pipeline restarts services.".encode())

    async with async_session_factory() as db:
        spanish = await search_documents(db, "base de datos", limit=5)
        english = await search_documents(db, "deploying", limit=5)
        pipeline = await search_documents(db, "pipeline", limit=5)

    assert [hit.title for hit in spanish] == ["Bases de datos"]
    assert "Postgres" in spanish[0].snippet and "\n" not in spanish[0].snippet
    assert [hit.title for hit in english] == ["Deployment"]
    assert [hit.title for hit in pipeline] == ["Deployment"]


async def test_disabled_documents_are_not_searchable(client):
    await authed_client(client)
    doc_id = await _add(client, "secreto.md", "# Secreto\n\nLa revisión trimestral es el día 3.".encode())
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    await client.patch(f"/api/v1/admin/kb/{doc_id}", json={"is_enabled": False}, headers=headers)

    async with async_session_factory() as db:
        assert await search_documents(db, "revisión trimestral", limit=5) == []


async def test_blank_or_punctuation_queries_find_nothing(client):
    await authed_client(client)
    await _add(client, "a.md", b"# A\n\ntexto cualquiera")
    async with async_session_factory() as db:
        assert await search_documents(db, "   ", limit=5) == []
        assert await search_documents(db, "!!! ???", limit=5) == []


async def test_scanned_pdfs_without_text_are_stored_but_never_match(client):
    await authed_client(client)
    resp = (
        await client.post(
            "/api/v1/admin/kb",
            files=[("files", ("manual.pdf", make_pdf("Acceso al correo"), "application/pdf"))],
            headers={"X-CSRF-Token": csrf_from_client(client)},
        )
    ).json()
    assert resp["documents"][0]["text_chars"] > 0
    async with async_session_factory() as db:
        hits = await search_documents(db, "correo", limit=5)
        assert [hit.title for hit in hits] == ["manual"]
        rows = (await db.execute(KbDocument.__table__.select())).all()
        assert len(rows) == 1
