"""Admin de la base de conocimiento: RBAC, CSRF, auditoría y la copia que ve el agente en /kb/."""

import uuid

from sqlalchemy import select

from app.agent.persistence import get_agent_storage
from app.db import async_session_factory
from app.models.audit import AuditLog
from app.models.kb import KbDocument
from app.models.user import UserRole
from tests.conftest import csrf_from_client
from tests.helpers import authed_client, create_user, insert_session
from tests.kb_fakes import make_pdf

GUIA = "# Guía de despliegue\n\nSe despliega con el pipeline del equipo cada martes."


async def _upload(client, files):
    return await client.post(
        "/api/v1/admin/kb",
        files=[("files", (name, data, content_type)) for name, data, content_type in files],
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )


async def _mirror(key: str):
    item = await get_agent_storage().store.aget(("kb",), key)
    return None if item is None else item.value


async def _audit(action: str) -> list[AuditLog]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(AuditLog).where(AuditLog.action == action))).scalars()
        )


# --- RBAC y CSRF --------------------------------------------------------------------------


async def test_kb_admin_requires_a_session(client):
    assert (await client.get("/api/v1/admin/kb")).status_code == 401


async def test_kb_admin_is_admin_only(client):
    user = await create_user(email="regular@example.com", role=UserRole.regular)
    session = await insert_session(user.id)
    client.cookies.set("sofee_session", str(session.id))
    assert (await client.get("/api/v1/admin/kb")).status_code == 403
    assert (await client.get("/api/v1/admin/integrations/tavily")).status_code == 403


async def test_kb_mutations_require_csrf(client):
    await authed_client(client)
    resp = await client.post("/api/v1/admin/kb", files=[("files", ("a.md", b"x", "text/markdown"))])
    assert resp.status_code == 403
    resp = await client.patch(f"/api/v1/admin/kb/{uuid.uuid4()}", json={"is_enabled": False})
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/admin/kb/{uuid.uuid4()}")
    assert resp.status_code == 403


# --- subida -------------------------------------------------------------------------------


async def test_upload_many_files_creates_documents_and_reports_rejections(client):
    await authed_client(client)
    resp = await _upload(
        client,
        [
            ("despliegue.md", GUIA.encode(), "text/markdown"),
            ("manual.pdf", make_pdf("Acceso al correo corporativo"), "application/pdf"),
            ("imagen.png", b"\x89PNG", "image/png"),
            ("roto.pdf", b"no es un pdf", "application/pdf"),
        ],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    titles = sorted(doc["title"] for doc in body["documents"])
    assert titles == ["Guía de despliegue", "manual"]
    assert {r["filename"]: r["reason"] for r in body["rejected"]} == {
        "imagen.png": "unsupported_type",
        "roto.pdf": "extraction_failed",
    }
    by_title = {doc["title"]: doc for doc in body["documents"]}
    assert by_title["Guía de despliegue"]["path"] == "/kb/despliegue.md"
    assert by_title["Guía de despliegue"]["text_chars"] == len(GUIA)
    assert by_title["manual"]["text_chars"] > 0

    # Solo los que se crearon llegan al store del agente, con la forma de StoreBackend.
    mirror = await _mirror("/despliegue.md")
    assert mirror is not None and mirror["content"] == GUIA and mirror["encoding"] == "utf-8"
    assert await _mirror("/imagen.md") is None
    assert len(await _audit("kb.document_uploaded")) == 2


async def test_slugs_stay_unique_when_the_same_name_is_uploaded_again(client):
    await authed_client(client)
    await _upload(client, [("Guía.md", b"# Uno", "text/markdown")])
    resp = await _upload(client, [("Guía.md", b"# Dos", "text/markdown"), ("guía.md", b"# Tres", "text/markdown")])
    slugs = sorted(doc["slug"] for doc in resp.json()["documents"])
    assert slugs == ["guia-2", "guia-3"]


async def test_oversized_files_are_rejected_not_truncated(client, monkeypatch):
    from app.config import settings

    await authed_client(client)
    monkeypatch.setattr(settings, "storage_max_upload_bytes", 10)
    resp = await _upload(client, [("grande.md", b"x" * 50, "text/markdown")])
    assert resp.json()["documents"] == []
    assert resp.json()["rejected"] == [{"filename": "grande.md", "reason": "too_large"}]


# --- listado, edición, vista previa y borrado --------------------------------------------


async def test_list_preview_edit_disable_and_delete_keep_the_agent_copy_in_sync(client):
    await authed_client(client)
    doc = (await _upload(client, [("despliegue.md", GUIA.encode(), "text/markdown")])).json()["documents"][0]
    headers = {"X-CSRF-Token": csrf_from_client(client)}

    listed = (await client.get("/api/v1/admin/kb")).json()
    assert [item["id"] for item in listed] == [doc["id"]]
    assert listed[0]["text_chars"] == len(GUIA)
    assert "text" not in listed[0]
    assert [item["id"] for item in (await client.get("/api/v1/admin/kb", params={"q": "guía"})).json()] == [doc["id"]]
    assert (await client.get("/api/v1/admin/kb", params={"q": "zzz"})).json() == []

    preview = (await client.get(f"/api/v1/admin/kb/{doc['id']}/text")).json()
    assert preview == {"id": doc["id"], "title": "Guía de despliegue", "text": GUIA, "text_chars": len(GUIA), "truncated": False}

    edited = await client.patch(
        f"/api/v1/admin/kb/{doc['id']}",
        json={"title": "Despliegue", "tags": [" equipo ", "equipo", "devops"]},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Despliegue"
    assert edited.json()["tags"] == ["equipo", "devops"]
    assert (await _mirror("/despliegue.md")) is not None

    disabled = await client.patch(f"/api/v1/admin/kb/{doc['id']}", json={"is_enabled": False}, headers=headers)
    assert disabled.json()["is_enabled"] is False
    assert await _mirror("/despliegue.md") is None

    # Un null explícito no cambia nada; volver a activarlo recrea la copia del agente.
    still_off = await client.patch(f"/api/v1/admin/kb/{doc['id']}", json={"is_enabled": None}, headers=headers)
    assert still_off.json()["is_enabled"] is False
    enabled = await client.patch(f"/api/v1/admin/kb/{doc['id']}", json={"is_enabled": True}, headers=headers)
    assert enabled.json()["is_enabled"] is True
    assert (await _mirror("/despliegue.md")) is not None

    deleted = await client.delete(f"/api/v1/admin/kb/{doc['id']}", headers=headers)
    assert deleted.status_code == 204
    assert await _mirror("/despliegue.md") is None
    async with async_session_factory() as db:
        assert (await db.execute(select(KbDocument))).scalars().all() == []
    # Cuatro PATCH con efecto o sin él; cada mutación queda auditada, también la que no cambia nada.
    assert len(await _audit("kb.document_updated")) == 4
    assert len(await _audit("kb.document_deleted")) == 1


async def test_preview_is_capped_for_long_documents(client, monkeypatch):
    from app.api.routes import kb_admin

    await authed_client(client)
    monkeypatch.setattr(kb_admin, "PREVIEW_CHARS", 20)
    doc = (await _upload(client, [("largo.txt", b"abcdefghij" * 3, "text/plain")])).json()["documents"][0]
    preview = (await client.get(f"/api/v1/admin/kb/{doc['id']}/text")).json()
    assert preview["text"] == "abcdefghijabcdefghij"
    assert preview["truncated"] is True
    assert preview["text_chars"] == 30


async def test_a_blank_title_is_refused_and_the_title_is_trimmed(client):
    await authed_client(client)
    doc = (await _upload(client, [("a.md", b"# Titulo", "text/markdown")])).json()["documents"][0]
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    blank = await client.patch(f"/api/v1/admin/kb/{doc['id']}", json={"title": "   "}, headers=headers)
    assert blank.status_code == 422
    trimmed = await client.patch(f"/api/v1/admin/kb/{doc['id']}", json={"title": "  Nuevo  "}, headers=headers)
    assert trimmed.json()["title"] == "Nuevo"


async def test_unknown_documents_answer_404(client):
    await authed_client(client)
    headers = {"X-CSRF-Token": csrf_from_client(client)}
    missing = uuid.uuid4()
    assert (await client.get(f"/api/v1/admin/kb/{missing}/text")).status_code == 404
    assert (await client.patch(f"/api/v1/admin/kb/{missing}", json={"is_enabled": False}, headers=headers)).status_code == 404
    assert (await client.delete(f"/api/v1/admin/kb/{missing}", headers=headers)).status_code == 404
