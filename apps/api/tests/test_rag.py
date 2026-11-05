"""RAG sobre la base de conocimiento: troceado, cliente de embeddings, indexado y recuperación.

Sin red: respx hace de servidor de embeddings. El "modelo" falso mide cuántas palabras de cada
tema aparecen en el texto, así que dos frases sobre lo mismo se parecen aunque no compartan ni
una palabra: justo lo que el full-text no puede hacer.
"""

import json
import math

import httpx
import pytest
import respx
from sqlalchemy import func, select

from app.config import settings
from app.db import async_session_factory
from app.models.kb import KbChunk, KbDocument
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingsError, embed_texts
from app.services.knowledge import search_documents
from app.services.rag import index_document, reindex_all, retrieve
from tests.conftest import csrf_from_client
from tests.helpers import authed_client

EMBEDDINGS_URL = "http://embeddings.test/v1"

TOPICS = [
    ("despliegue", "deploy", "release", "ship", "publicar", "lanzar", "pipeline"),
    ("guardia", "oncall", "incidente", "pager", "escalado", "alerta"),
    ("cafe", "cafetera", "cocina", "desayuno"),
]


def _vector(text: str) -> list[float]:
    lowered = text.lower()
    vector = [float(sum(lowered.count(word) for word in words)) for words in TOPICS]
    return vector if any(vector) else [0.0, 0.0, 0.01]


class _Calls(list):
    router: respx.MockRouter


@pytest.fixture
def embeddings(monkeypatch):
    """Servidor de embeddings falso. `calls` guarda cada petición para inspeccionarla."""
    monkeypatch.setattr(settings, "embeddings_base_url", EMBEDDINGS_URL)
    monkeypatch.setattr(settings, "embeddings_model", "fake-embed")
    # Los vectores falsos tienen otra escala que un modelo real: la barrera se prueba aparte.
    monkeypatch.setattr(settings, "rag_min_similarity", 0.0)
    calls = _Calls()

    def respond(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        calls.append(texts)
        data = [{"index": i, "embedding": _vector(t)} for i, t in enumerate(texts)]
        return httpx.Response(200, json={"data": data})

    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{EMBEDDINGS_URL}/embeddings").mock(side_effect=respond)
        calls.router = mock  # para añadir más rutas (p. ej. Tavily) sin anidar mocks
        yield calls


async def _upload(client, name: str, body: str) -> str:
    resp = await client.post(
        "/api/v1/admin/kb",
        files=[("files", (name, body.encode(), "text/markdown"))],
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["documents"][0]["id"]


DEPLOY = "# Despliegue\n\n## Pipeline\n\nCada martes el pipeline publica una release en producción."
ONCALL = "# Guardia\n\n## Escalado\n\nSi suena el pager, escala el incidente al secundario."
COFFEE = "# Café\n\nLa cafetera está en la cocina, junto al desayuno."


# --- troceado ---------------------------------------------------------------------------


def test_chunks_keep_the_heading_they_live_under():
    text = "# Guía\n\nIntro de la guía con algo de texto suficiente.\n\n## Deploy\n\nCómo se despliega el servicio cada martes."
    chunks = chunk_text(text, max_chars=500, overlap_chars=0)
    assert [(c.position, c.heading) for c in chunks] == [(0, "Guía"), (1, "Deploy")]
    assert "despliega" in chunks[1].text and "Intro" not in chunks[1].text


def test_long_sections_split_on_paragraphs_with_overlap_inside_the_section():
    paragraphs = [f"Párrafo número {n} " + "palabra " * 12 for n in range(6)]
    chunks = chunk_text("## Tema\n\n" + "\n\n".join(paragraphs), max_chars=250, overlap_chars=60)
    assert len(chunks) >= 3
    assert all(c.heading == "Tema" for c in chunks)
    assert all(len(c.text) <= 250 + 60 + 1 for c in chunks)
    assert chunks[1].text.startswith(chunks[0].text.split("\n\n")[-1][-60:].strip()[:20])


def test_text_without_headings_and_empty_text():
    assert chunk_text("", max_chars=200, overlap_chars=20) == []
    only = chunk_text("Un texto plano sin encabezados pero con longitud suficiente.", max_chars=200, overlap_chars=20)
    assert [c.heading for c in only] == [""]


def test_a_paragraph_longer_than_the_limit_is_cut_on_spaces():
    chunks = chunk_text("palabra " * 100, max_chars=100, overlap_chars=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 100 and not c.text.endswith("palab") for c in chunks)


# --- cliente de embeddings --------------------------------------------------------------


async def test_embed_texts_returns_unit_vectors_in_order_and_batches(embeddings):
    texts = [f"deploy {n}" for n in range(20)] + ["cafetera"]
    vectors = await embed_texts(texts)
    assert len(vectors) == 21
    assert [len(batch) for batch in embeddings] == [16, 5]
    assert all(math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-9) for vec in vectors)
    assert vectors[-1][2] == pytest.approx(1.0)


async def test_embed_texts_reports_a_failing_service(monkeypatch):
    monkeypatch.setattr(settings, "embeddings_base_url", EMBEDDINGS_URL)
    monkeypatch.setattr(settings, "embeddings_model", "fake-embed")
    with respx.mock() as mock:
        mock.post(f"{EMBEDDINGS_URL}/embeddings").mock(return_value=httpx.Response(500))
        with pytest.raises(EmbeddingsError):
            await embed_texts(["hola"])


async def test_embed_texts_refuses_when_not_configured():
    with pytest.raises(EmbeddingsError):
        await embed_texts(["hola"])


# --- indexado y recuperación ------------------------------------------------------------


async def test_a_paraphrased_question_finds_the_passage_that_full_text_cannot(client, embeddings):
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    await _upload(client, "guardia.md", ONCALL)
    await _upload(client, "cafe.md", COFFEE)

    query = "how do we ship to prod"  # ninguna palabra en común con el documento
    async with async_session_factory() as db:
        assert await search_documents(db, query, limit=5) == []
        hits = await retrieve(db, query, limit=3)

    assert hits is not None and hits[0].title == "Despliegue"
    assert hits[0].heading == "Pipeline" and "release" in hits[0].text
    assert "Café" not in [h.title for h in hits]


async def test_an_exact_term_breaks_a_tie_between_equally_similar_chunks(client, embeddings):
    await authed_client(client)
    await _upload(client, "guardia.md", "# Guardia\n\nLa severidad SEV1 llama al primario de inmediato.")
    await _upload(client, "despliegue.md", DEPLOY)

    async with async_session_factory() as db:
        # Los vectores falsos no distinguen "SEV1": solo el full-text puede desempatar.
        hits = await retrieve(db, "SEV1 ahora mismo por favor", limit=3)

    assert hits is not None and hits[0].title == "Guardia"


async def test_disabled_documents_are_not_retrieved_and_chunks_go_with_the_document(client, embeddings):
    await authed_client(client)
    deploy_id = await _upload(client, "despliegue.md", DEPLOY)
    await _upload(client, "guardia.md", ONCALL)

    off = await client.patch(
        f"/api/v1/admin/kb/{deploy_id}",
        json={"is_enabled": False},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert off.status_code == 200
    async with async_session_factory() as db:
        hits = await retrieve(db, "release pipeline", limit=5)
    assert hits is not None and "Despliegue" not in [h.title for h in hits]

    gone = await client.delete(
        f"/api/v1/admin/kb/{deploy_id}", headers={"X-CSRF-Token": csrf_from_client(client)}
    )
    assert gone.status_code == 204
    async with async_session_factory() as db:
        remaining = (await db.execute(select(func.count()).select_from(KbChunk))).scalar_one()
    assert remaining == 1  # solo el de Guardia


async def test_reindexing_replaces_chunks_instead_of_duplicating_them(client, embeddings):
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    async with async_session_factory() as db:
        before = (await db.execute(select(func.count()).select_from(KbChunk))).scalar_one()
        documents, chunks = await reindex_all(db)
        await db.commit()
        after = (await db.execute(select(func.count()).select_from(KbChunk))).scalar_one()
    assert (documents, chunks) == (1, before) and after == before


async def test_chunks_from_another_model_are_ignored_until_reindexed(client, embeddings, monkeypatch):
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    monkeypatch.setattr(settings, "embeddings_model", "otro-modelo")
    async with async_session_factory() as db:
        assert await retrieve(db, "release", limit=3) is None
        document = (await db.execute(select(KbDocument))).scalar_one()
        await index_document(db, document)
        await db.commit()
        hits = await retrieve(db, "release", limit=3)
    assert hits is not None and hits[0].title == "Despliegue"


# --- sin RAG: todo sigue funcionando -----------------------------------------------------


async def test_without_embeddings_retrieve_steps_aside_and_uploads_still_work(client):
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    async with async_session_factory() as db:
        assert await retrieve(db, "release", limit=3) is None
        assert (await db.execute(select(func.count()).select_from(KbChunk))).scalar_one() == 0


async def test_an_upload_succeeds_and_stays_searchable_when_the_embeddings_service_is_down(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "embeddings_base_url", EMBEDDINGS_URL)
    monkeypatch.setattr(settings, "embeddings_model", "fake-embed")
    await authed_client(client)
    with respx.mock() as mock:
        mock.post(f"{EMBEDDINGS_URL}/embeddings").mock(return_value=httpx.Response(503))
        await _upload(client, "despliegue.md", DEPLOY)
        async with async_session_factory() as db:
            assert (await db.execute(select(func.count()).select_from(KbChunk))).scalar_one() == 0
            assert [h.title for h in await search_documents(db, "pipeline", limit=3)] == ["Despliegue"]
            assert await retrieve(db, "pipeline", limit=3) is None


async def test_the_query_prefix_goes_on_questions_but_never_on_documents(client, embeddings, monkeypatch):
    monkeypatch.setattr(settings, "embeddings_query_prefix", "Instruct: busca\\nQuery: ")
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    assert not any(text.startswith("Instruct:") for batch in embeddings for text in batch)

    async with async_session_factory() as db:
        await retrieve(db, "release", limit=3)
    assert embeddings[-1] == ["Instruct: busca\nQuery: release"]


async def test_a_question_the_documents_do_not_answer_retrieves_nothing(client, embeddings, monkeypatch):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    await _upload(client, "guardia.md", ONCALL)

    async with async_session_factory() as db:
        assert await retrieve(db, "capital de Francia", limit=5) == []  # no toca ningún tema
        # Una palabra suelta que sí está en el texto no rescata un trozo sin parecido.
        assert await retrieve(db, "producción", limit=5) == []
        hits = await retrieve(db, "release pipeline", limit=5)
    assert hits and hits[0].title == "Despliegue"


async def test_only_chunks_close_to_the_best_one_are_returned(client, embeddings, monkeypatch):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    monkeypatch.setattr(settings, "rag_similarity_margin", 0.1)
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    await _upload(client, "guardia.md", ONCALL)

    async with async_session_factory() as db:
        hits = await retrieve(db, "release pipeline", limit=5)
    assert hits is not None and [h.title for h in hits] == ["Despliegue"]


async def test_a_very_short_query_needs_more_similarity_than_a_full_question(client, embeddings, monkeypatch):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.68)  # "release guardia" empata a ~0.707 con cada tema
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)

    async with async_session_factory() as db:
        assert await retrieve(db, "release guardia", limit=5) == []  # 2 palabras: exige 0.75
        hits = await retrieve(db, "release guardia hoy mismo", limit=5)  # 4 palabras: basta 0.68
    assert hits and hits[0].title == "Despliegue"


async def test_a_short_query_naming_a_document_title_finds_that_document_even_below_the_barrier(
    client, embeddings, monkeypatch
):
    monkeypatch.setattr(settings, "rag_min_similarity", 1.5)  # ningún trozo llega por parecido
    await authed_client(client)
    await _upload(client, "despliegue.md", DEPLOY)
    await _upload(client, "guardia.md", ONCALL)

    async with async_session_factory() as db:
        by_title = await retrieve(db, "guardia", limit=5)
        not_a_title = await retrieve(db, "escalado secundario", limit=5)  # está en el texto, no en el título

    assert by_title and {h.title for h in by_title} == {"Guardia"}
    assert not_a_title == []
