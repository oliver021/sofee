"""Recuperación automática: el agente recibe los pasajes aunque el modelo no llame a la búsqueda."""


import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.executor import executor
from app.agent.grounding import build_retrieval_query
from app.agent.history import SUMMARY_HEADER
from app.config import settings
from app.services.tavily import TAVILY_SEARCH_URL
from tests.agent_fakes import ScriptedChatModel, ai
from tests.conftest import csrf_from_client
from tests.helpers import authed_client

# Mismos helpers y fixtures que test_knowledge_runs.py y test_rag.py.
from tests.test_knowledge_runs import _drain_runs, _events, _start, _thread, _upload_kb, use_model  # noqa: F401
from tests.test_rag import DEPLOY, ONCALL, embeddings  # noqa: F401


async def _ask(client, use_model, text: str):
    model = ScriptedChatModel(script=[ai("Listo [1].")], seen=[])
    use_model(model)
    run_id = (await _start(client, text=text)).json()["run_id"]
    await executor.wait(run_id)
    return model, await _events(run_id)


def _system_text(model) -> str:
    return "\n".join(m.text for m in model.seen[0] if m.type == "system")


async def test_the_model_gets_the_matching_passages_and_they_become_numbered_sources(
    client, use_model, embeddings  # noqa: F811
):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _upload_kb(client, "guardia.md", ONCALL)
    await _thread(client)

    model, events = await _ask(client, use_model, "how do we ship to prod")  # sin palabras en común

    system = _system_text(model)
    assert "Passages retrieved from the team documentation" in system
    assert "[1] Despliegue › Pipeline" in system and "release" in system
    added = [payload for kind, payload in events if kind == "source.added"]
    assert added and added[0]["kind"] == "kb" and added[0]["index"] == 1
    assert added[0]["title"] == "Despliegue"


async def test_the_passages_are_retrieved_once_per_run(client, use_model, embeddings):  # noqa: F811
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _thread(client)
    await _ask(client, use_model, "release")
    question_calls = [batch for batch in embeddings if batch and "release" in batch[0] and "pipeline" not in batch[0]]
    assert len(question_calls) == 1


async def test_without_embeddings_the_prompt_is_untouched(client, use_model):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _thread(client)

    model, events = await _ask(client, use_model, "pipeline")

    assert "Passages retrieved" not in _system_text(model)
    assert not [1 for kind, _ in events if kind == "source.added"]


async def test_a_question_the_documents_do_not_answer_tells_the_model_not_to_answer_from_memory(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _thread(client)

    model, events = await _ask(client, use_model, "capital de Francia")

    assert "No passage of the team documentation matches" in _system_text(model)
    assert not [1 for kind, _ in events if kind == "source.added"]


def test_a_short_follow_up_is_searched_together_with_the_question_before_it():
    history = [
        HumanMessage(content="Busca en la web qué son las proyecciones de Futamura"),
        AIMessage(content="Son tres niveles."),
        HumanMessage(content="Cuál es la tercera proyección"),
    ]
    assert build_retrieval_query(history) == (
        "Busca en la web qué son las proyecciones de Futamura\nCuál es la tercera proyección"
    )


def test_a_self_contained_question_is_searched_alone_and_summaries_are_not_questions():
    long_question = "Cómo se despliega un servicio nuevo en producción cada martes"
    history = [
        HumanMessage(content=f"{SUMMARY_HEADER}\nresumen"),
        HumanMessage(content="otra cosa distinta"),
        HumanMessage(content=long_question),
    ]
    assert build_retrieval_query(history) == long_question
    assert build_retrieval_query([HumanMessage(content=f"{SUMMARY_HEADER}\nresumen")]) == ""
    assert build_retrieval_query([HumanMessage(content="¿y la tercera?")]) == "¿y la tercera?"


TAVILY_RESULTS = {
    "results": [
        {
            "title": "Proyecciones de Futamura",
            "url": "https://es.wikipedia.org/wiki/Proyecciones_de_Futamura",
            "content": "La tercera proyección genera un generador de compiladores.",
        }
    ]
}


async def _tavily_key(client) -> None:
    resp = await client.put(
        "/api/v1/admin/integrations/tavily",
        json={"api_key": "tvly-prueba-9999"},
        headers={"X-CSRF-Token": csrf_from_client(client)},
    )
    assert resp.status_code == 200, resp.text


class _FailsOnce(ScriptedChatModel):
    """El primer `ainvoke` (la reescritura de la consulta) falla; la respuesta final sale normal."""

    def _fail_first(self, messages) -> None:  # noqa: ANN001
        if not self.seen:
            self.seen.append(list(messages))
            raise RuntimeError("modelo caído")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN201
        self._fail_first(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN201
        # Dentro del grafo, `ainvoke` pasa por el camino de streaming del modelo.
        self._fail_first(messages)
        yield from super()._stream(messages, stop, run_manager, **kwargs)


async def _ask_explore(client, use_model, text: str, *, rewrite: str | None = None, model_cls=ScriptedChatModel):
    """`rewrite` es lo que responde el modelo a la reescritura de la consulta web (una llamada previa)."""
    script = ([ai(rewrite)] if rewrite is not None else []) + [ai("Listo [1].")]
    model = model_cls(script=script, seen=[])
    use_model(model)
    run_id = (await _start(client, mode="explore", text=text)).json()["run_id"]
    await executor.wait(run_id)
    return model, await _events(run_id)


async def test_explore_searches_the_web_before_answering_when_the_team_docs_have_nothing(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _tavily_key(client)
    await _thread(client, mode="explore")
    route = embeddings.router.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=TAVILY_RESULTS)
    )

    model, events = await _ask_explore(
        client, use_model, "capital de Francia", rewrite="capital city of France"
    )

    assert route.call_count == 1
    system = "\n".join(m.text for m in model.seen[-1] if m.type == "system")
    assert "web results were searched" in system and "[1] Proyecciones de Futamura" in system
    # La reescritura de la consulta es interna: sus tokens no llegan al texto de la respuesta.
    streamed = "".join(p["text"] for kind, p in events if kind == "message.delta")
    assert "capital city" not in streamed and streamed.strip() == "Listo [1]."
    added = [payload for kind, payload in events if kind == "source.added"]
    assert [(p["kind"], p["index"]) for p in added] == [("web", 1)]


async def test_no_web_search_when_the_team_docs_answer_or_there_is_no_tavily_key(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _thread(client, mode="explore")
    route = embeddings.router.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=TAVILY_RESULTS)
    )

    # Sin clave de Tavily: no hay web_search y el harness no busca.
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    model, _ = await _ask_explore(client, use_model, "capital de Francia")
    assert route.call_count == 0
    assert "No passage of the team documentation matches" in _system_text(model)


async def test_the_web_is_not_searched_when_the_documents_do_answer(
    client, use_model, embeddings  # noqa: F811
):
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _tavily_key(client)
    await _thread(client, mode="explore")
    route = embeddings.router.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=TAVILY_RESULTS)
    )

    model, _ = await _ask_explore(client, use_model, "release pipeline")

    assert route.call_count == 0
    assert "Passages retrieved from the team documentation" in _system_text(model)


async def test_a_failing_web_search_falls_back_to_the_no_match_notice(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _tavily_key(client)
    await _thread(client, mode="explore")
    embeddings.router.post(TAVILY_SEARCH_URL).mock(return_value=httpx.Response(500))

    model, events = await _ask_explore(
        client, use_model, "capital de Francia", rewrite="capital city of France"
    )

    system = "\n".join(m.text for m in model.seen[-1] if m.type == "system")
    assert "No passage of the team documentation matches" in system
    assert not [1 for kind, _ in events if kind == "source.added"]


async def test_the_web_query_is_rewritten_by_the_model_with_the_thread_context(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _tavily_key(client)
    await _thread(client, mode="explore")
    route = embeddings.router.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=TAVILY_RESULTS)
    )

    model, _ = await _ask_explore(
        client, use_model, "Cuál es la tercera proyección", rewrite='"Futamura third projection compiler generator"\nporque sí'
    )

    sent = json.loads(route.calls.last.request.content)["query"]
    assert sent == "Futamura third projection compiler generator"  # una línea, sin comillas
    rewrite_call = model.seen[0]
    assert rewrite_call[0].type == "system" and "search query" in rewrite_call[0].text
    assert "Cuál es la tercera proyección" in rewrite_call[1].text


async def test_if_the_rewrite_fails_the_web_is_searched_with_the_question_as_asked(
    client, use_model, embeddings, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(settings, "rag_min_similarity", 0.5)
    await authed_client(client)
    await _upload_kb(client, "despliegue.md", DEPLOY)
    await _tavily_key(client)
    await _thread(client, mode="explore")
    route = embeddings.router.post(TAVILY_SEARCH_URL).mock(
        return_value=httpx.Response(200, json=TAVILY_RESULTS)
    )

    await _ask_explore(client, use_model, "capital de Francia", model_cls=_FailsOnce)

    assert json.loads(route.calls.last.request.content)["query"] == "capital de Francia"
