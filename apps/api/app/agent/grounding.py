"""Recuperación automática (RAG) antes de cada respuesta del agente principal.

Un modelo pequeño no siempre decide buscar en la documentación. Este middleware recupera los
pasajes de la última pregunta, los registra como fuentes del run (misma numeración `[n]` que las
herramientas) y los añade al prompt de sistema de la llamada. No se guardan en el historial.
La recuperación se hace una vez por run: las siguientes llamadas del modelo reutilizan el bloque.
"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.constants import TAG_NOSTREAM

from urllib.parse import urlsplit

from ..db import async_session_factory
from ..services.integrations import TAVILY, active_secret
from ..services.rag import retrieve
from ..services.tavily import TavilyError, tavily_search
from .history import SUMMARY_HEADER
from .sources import get_registry, strip_citation_markers

GROUNDING_LIMIT = 4
_QUERY_CAP = 300
_PASSAGE_CAP = 900
# Una pregunta de menos palabras que esto ("¿y la tercera?") no se entiende sin la anterior.
_SHORT_QUESTION_WORDS = 6

_HEADER = (
    "Passages retrieved from the team documentation for the user's latest question. They are "
    "already numbered: cite them as [n] using only these numbers. Use only the passages that "
    "really answer the question and ignore the rest. If they do not cover it, do not answer from "
    "memory as if it were verified: say what is missing, or look it up with your search tools "
    "(web_search for general or public knowledge).\n"
)
_WEB_HEADER = (
    "The team documentation has nothing on the user's latest question, so these web results were "
    "searched for it. They are already numbered: cite them as [n] using only these numbers. Answer "
    "only from what they say; do not add facts from memory, and if they do not answer the question, "
    "say so.\n"
)
_WEB_RESULTS = 4
_WEB_SNIPPET_CAP = 500
_REWRITE_PROMPT = (
    "You write web search queries. Given a conversation, reply with ONE standalone search query "
    "(at most 12 words) for the user's latest question. Resolve references like 'the third one' "
    "using the conversation, keep proper nouns, and add the field or domain when a term is "
    "ambiguous (for example 'Futamura projections partial evaluation compilers'). Use the language "
    "that will find the best sources: English for technical topics. Reply with the query only: no "
    "quotes, no explanation."
)
_REWRITE_TURNS = 4
_REWRITE_TURN_CAP = 300
_NO_MATCH = (
    "No passage of the team documentation matches the user's latest question. If it is about the "
    "team, say you found nothing. If it is general knowledge, do not answer it from memory: use "
    "web_search when you have it, and otherwise say you could not verify it.\n"
)


class GroundingMiddleware(AgentMiddleware):
    """Añade al system prompt los pasajes de la base de conocimiento que responden a la pregunta.

    Con `web_fallback`, si la base no tiene nada sobre la pregunta busca en la web antes de que el
    modelo responda: un modelo pequeño no siempre decide usar `web_search` y acaba contestando de
    memoria. Esa búsqueda cuenta contra `max_searches` del perfil.
    """

    def __init__(self, *, web_fallback: bool = False, max_searches: int = 3) -> None:
        super().__init__()
        self.web_fallback = web_fallback
        self.max_searches = max_searches

    async def awrap_model_call(self, request, handler):  # noqa: ANN001, ANN201
        block = await self._block(request)
        if block:
            system = request.system_message
            text = f"{system.text}\n\n{block}" if system is not None else block
            request = request.override(system_message=SystemMessage(content=text))
        return await handler(request)

    async def _block(self, request) -> str:  # noqa: ANN001
        registry = get_registry(request.runtime.context.run_id)
        if registry.grounding is not None:
            return registry.grounding
        question = build_retrieval_query(request.messages)
        block = ""
        if question:
            async with async_session_factory() as db:
                passages = await retrieve(db, question[-_QUERY_CAP:], limit=GROUNDING_LIMIT)
            lines = []
            if passages == []:
                block = await self._web_block(request, question) or _NO_MATCH
            for passage in passages or []:
                label = f"{passage.title} › {passage.heading}" if passage.heading else passage.title
                index = registry.add(
                    kind="kb", title=passage.title, ref=passage.document_id, snippet=passage.text[:300]
                )
                lines.append(f"[{index}] {label} — {passage.text[:_PASSAGE_CAP]}")
            if lines:
                block = _HEADER + "\n".join(lines)
        registry.grounding = block
        return block


    async def _web_block(self, request, question: str) -> str:  # noqa: ANN001
        """Resultados web numerados, o `""` si no se puede (sin permiso, sin clave, sin presupuesto, error)."""
        registry = get_registry(request.runtime.context.run_id)
        if not self.web_fallback or registry.searches >= self.max_searches:
            return ""
        async with async_session_factory() as db:
            api_key = await active_secret(db, TAVILY)
        if api_key is None:
            return ""
        registry.searches += 1
        request.runtime.stream_writer({"type": "status", "text": "Buscando en la web"})
        query = await _web_query(request, question)
        try:
            results = await tavily_search(api_key, query, max_results=_WEB_RESULTS)
        except TavilyError:
            return ""
        lines = []
        for result in results:
            snippet = " ".join(result.content.split())[:_WEB_SNIPPET_CAP]
            index = registry.add(kind="web", title=result.title, url=result.url, snippet=snippet)
            lines.append(f"[{index}] {result.title} — {urlsplit(result.url).netloc or result.url}\n{snippet}")
        return _WEB_HEADER + "\n".join(lines) if lines else ""


async def _web_query(request, question: str) -> str:  # noqa: ANN001
    """Consulta para el buscador web: el modelo reescribe la pregunta con el contexto del hilo.

    Una pregunta suelta ("¿cuál es la tercera proyección de Futamura?") es ambigua para un buscador.
    Si el modelo falla o no devuelve nada útil, se busca con la pregunta tal cual.
    """
    fallback = " ".join(question.split())[-_QUERY_CAP:]
    try:
        # `nostream`: la reescritura es interna, sus tokens no deben salir en el texto de la respuesta.
        reply = await request.model.with_config(tags=[TAG_NOSTREAM]).ainvoke(
            [
                SystemMessage(content=_REWRITE_PROMPT),
                HumanMessage(content=_conversation_excerpt(request.messages)),
            ]
        )
    except Exception:  # noqa: BLE001 - cualquier fallo del modelo se resuelve buscando con la pregunta
        return fallback
    lines = [line.strip().strip("\"'`") for line in reply.text.splitlines() if line.strip()]
    query = lines[0] if lines else ""
    return query[:_QUERY_CAP] if len(query.split()) >= 2 else fallback


def _conversation_excerpt(messages) -> str:  # noqa: ANN001
    """Últimos turnos de la conversación como texto, recortados."""
    turns = []
    for message in messages[-_REWRITE_TURNS:]:
        if isinstance(message, HumanMessage):
            turns.append(f"User: {message.text.strip()[:_REWRITE_TURN_CAP]}")
        elif isinstance(message, AIMessage) and message.text.strip():
            turns.append(f"Assistant: {strip_citation_markers(message.text).strip()[:_REWRITE_TURN_CAP]}")
    return "\n".join(turns)


def build_retrieval_query(messages) -> str:  # noqa: ANN001
    """Texto con el que se busca: la última pregunta y, si es corta, la que la precede.

    "¿Cuál es la tercera?" no dice de qué habla; con la pregunta anterior delante sí.
    """
    questions = [
        message.text.strip()
        for message in messages
        if isinstance(message, HumanMessage) and not message.text.startswith(SUMMARY_HEADER)
    ]
    questions = [question for question in questions if question]
    if not questions:
        return ""
    last = questions[-1]
    if len(last.split()) < _SHORT_QUESTION_WORDS and len(questions) > 1:
        return f"{questions[-2]}\n{last}"
    return last


__all__ = ["GROUNDING_LIMIT", "GroundingMiddleware", "build_retrieval_query"]
