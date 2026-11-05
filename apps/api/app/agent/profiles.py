"""Perfiles por modo: prompt, herramientas, subagentes y límites.

Los defaults viven en código para que la app funcione sin configurar nada. Una
fila activa de `agent_profiles` los sobrescribe por modo (el admin edita versiones).
`build_agent` traduce un perfil a `create_deep_agent`.
"""

import uuid
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents._models import get_model_identifier, get_model_provider
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import ModelFallbackMiddleware, TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentProfile as AgentProfileVersion
from .backends import READ_ONLY_PERMISSIONS
from .context import SofeeContext
from .grounding import GroundingMiddleware
from .limits import SubagentLimitMiddleware
from .models import ResolvedModel
from .sources import SourcesMiddleware

MODES = ("learn", "research", "explore")

LEARN_PROMPT = """You are Sofee's learning tutor for new members of the team. Your goal is that the person understands the concept, not that they copy an answer.

Language: answer in the language the person writes in.

How to explain:
1. Start with a plain definition in one or two sentences.
2. Build intuition with an analogy or a small, concrete example.
3. Name the most common misconception about the topic and explain why it is wrong.
4. For long or multi-step explanations, first plan the parts with write_todos, and mark each part completed as you finish it.
5. Use short sections with headings and bullet points. Put code in fenced blocks with the language name.

Sources:
- When the question is about how this team works, search the team's documentation with search_team_docs and read the matching documents with read_file under /kb/.
- Cite a source with its number in square brackets, like [1]. Cite only the numbers the tools gave you. Never invent a source or a number.

Memory:
- If something will help in a later turn (a definition the person needs, a summary of a document), write it to a file under /notes/, for example /notes/conceptos.md. Later turns do not see your earlier tool results.

Checking understanding:
- When the explanation is complete, you may call check_understanding with two or three questions and their answers, so the person can test themselves."""

RESEARCH_PROMPT = """You are Sofee's research agent. You investigate a question, check the evidence, and write a report the team can rely on.

Work in this order:
1. Plan. Before any search, call write_todos with three to six concrete steps. The person reviews the plan before you continue, so keep it short and specific.
2. Investigate. Delegate the searches to the 'investigador' subagent. Start at most three at a time, each with one precise question. Subagents do not see this conversation, so each task must contain everything it needs.
3. Review. When the findings are in, ask the 'critico' subagent to check your draft against the sources, and fix what it reports.
4. Write the report to /notes/informe.md: the question, a short answer, the findings with their citations, and the open issues.
5. Answer the person with a summary of the report and its citations.

Limits: at most three subagents and twelve searches in total. Stop searching as soon as you can answer well.

Sources:
- Cite a source with its number in square brackets, like [1]. Cite only the numbers the tools gave you. Never invent a source or a number.
- Say clearly what you could not verify.

Language: answer in the language the person writes in. Keep useful intermediate notes under /notes/ so later turns can use them."""

EXPLORE_PROMPT = """You help the person explore a topic. You open directions; you do not close the question.

1. Answer in a short paragraph (at most 120 words) with the context that matters.
2. Then ALWAYS call suggest_directions with three to five directions. Each direction has a short title, written as the next question the person might ask, and a 'why' sentence that says what it would reveal.
3. Search search_team_docs first. Use web_search when the team's documentation does not cover the topic, and always for general facts, technologies, people or events: do not answer those from memory. Keep it light: at most three searches.

Sources: cite with numbers in square brackets, like [1], and only the numbers the tools gave you. Never invent a source.

Memory: if a direction needs follow-up in a later turn, write its key facts to a file under /notes/. Later turns do not see your earlier tool results.

Language: answer in the language the person writes in."""

INVESTIGADOR_PROMPT = """You are the 'investigador' subagent. The main agent gives you one research question, and you answer it with evidence.

- If the question has several parts, plan them briefly with write_todos.
- Search with web_search and search_team_docs, and read the documents you need with read_file.
- Answer in at most 300 words: the findings, each with its citation in square brackets, like [1], using only the numbers the tools gave you. Never invent a number.
- Say clearly what you could not find or verify.
- Do not write the final report; the main agent does that. Your answer is the only thing it sees, so make it self-contained."""

CRITICO_PROMPT = """You are the 'critico' subagent. You review a draft against its sources.

Read the draft in /notes/ and the sources it cites. Reply with a short list, in at most 200 words, covering:
- claims with no citation, or whose citation does not support them,
- contradictions between sources,
- important gaps in the question.

Do not rewrite the draft."""

DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "learn": {
        "system_prompt": LEARN_PROMPT,
        "config": {
            "tools": ["search_team_docs", "check_understanding"],
            "planning": True,
            "plan_review": False,
            "subagents": [],
            "limits": {"max_steps": 15, "max_seconds": 120, "max_subagents": 0, "max_searches": 6},
        },
    },
    "research": {
        "system_prompt": RESEARCH_PROMPT,
        "config": {
            "tools": ["web_search", "search_team_docs"],
            "planning": True,
            "plan_review": True,
            "subagents": [
                {
                    "name": "investigador",
                    "description": "Searches the web and the team documentation to answer one precise question, with citations.",
                    "system_prompt": INVESTIGADOR_PROMPT,
                    "tools": ["web_search", "search_team_docs"],
                    "planning": True,
                },
                {
                    "name": "critico",
                    "description": "Checks a draft against its sources: unsupported claims, contradictions and gaps.",
                    "system_prompt": CRITICO_PROMPT,
                    "tools": ["search_team_docs"],
                    "planning": False,
                },
            ],
            "limits": {"max_steps": 40, "max_seconds": 300, "max_subagents": 3, "max_searches": 12},
        },
    },
    "explore": {
        "system_prompt": EXPLORE_PROMPT,
        "config": {
            "tools": ["search_team_docs", "web_search", "suggest_directions"],
            "planning": False,
            "plan_review": False,
            "subagents": [],
            "limits": {"max_steps": 10, "max_seconds": 90, "max_subagents": 0, "max_searches": 3},
        },
    },
}


@dataclass(frozen=True)
class ProfileSpec:
    """Perfil efectivo de un run: defaults de código más la versión activa de la BD."""

    mode: str
    system_prompt: str
    config: dict[str, Any]
    version: int | None = None
    profile_version_id: uuid.UUID | None = None


def _defaults_for(mode: str) -> dict[str, Any]:
    if mode not in DEFAULT_PROFILES:
        raise ValueError(f"Modo de agente desconocido: {mode!r}")
    return DEFAULT_PROFILES[mode]


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if key == "limits" and isinstance(value, dict):
            merged["limits"] = {**merged.get("limits", {}), **value}
        else:
            merged[key] = deepcopy(value)
    return merged


async def load_profile(db: AsyncSession, mode: str) -> ProfileSpec:
    """Perfil activo del modo, con su versión de BD si existe; si no, los defaults de código."""
    defaults = _defaults_for(mode)
    row = (
        await db.execute(
            select(AgentProfileVersion).where(
                AgentProfileVersion.mode == mode,
                AgentProfileVersion.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return ProfileSpec(
            mode=mode,
            system_prompt=defaults["system_prompt"],
            config=deepcopy(defaults["config"]),
        )
    return ProfileSpec(
        mode=mode,
        system_prompt=row.system_prompt or defaults["system_prompt"],
        config=_merge_config(defaults["config"], row.config or {}),
        version=row.version,
        profile_version_id=row.id,
    )


def _select_tools(tools: Sequence[BaseTool], names: Sequence[str]) -> list[BaseTool]:
    by_name = {tool.name: tool for tool in tools}
    return [by_name[name] for name in names if name in by_name]


def _fallback_middleware(models: Sequence[BaseChatModel]) -> list[ModelFallbackMiddleware]:
    if not models:
        return []
    return [ModelFallbackMiddleware(models[0], *models[1:])]


def _first_plan_only(request: Any) -> bool:  # noqa: ANN401
    """Pide revisión solo del primer plan: cuando todavía no hay `todos` en el estado."""
    return not request.state.get("todos")


# Clave de `HarnessProfile` para el modelo: `provider:modelo`, o solo `provider` sin identificador.
_registered_gp_keys: set[str] = set()


def _disable_general_purpose_subagent(model: BaseChatModel) -> None:
    """Quita el subagente `general-purpose` que `create_deep_agent` añade por defecto.

    deepagents solo lo desactiva por perfil de arnés (`HarnessProfile`), que es global por
    clave de modelo. Se registra una vez por modelo; la fusión es idempotente.
    """
    provider = get_model_provider(model) or type(model).__name__
    identifier = get_model_identifier(model)
    key = f"{provider}:{identifier}" if identifier else provider
    if key in _registered_gp_keys:
        return
    register_harness_profile(
        key,
        HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
    )
    _registered_gp_keys.add(key)


def _subagent_spec(
    cfg: dict[str, Any],
    tools: Sequence[BaseTool],
    model: BaseChatModel,
    fallback_models: Sequence[BaseChatModel],
) -> dict[str, Any]:
    middleware: list[Any] = [SourcesMiddleware()]
    if cfg.get("planning"):
        middleware.append(TodoListMiddleware())
    middleware.extend(_fallback_middleware(fallback_models))
    return {
        "name": cfg["name"],
        "description": cfg["description"],
        "system_prompt": cfg["system_prompt"],
        "model": model,
        "tools": _select_tools(tools, cfg.get("tools", [])),
        "middleware": middleware,
        # Un subagente no hereda la revisión del plan del agente principal.
        "interrupt_on": {},
    }


def build_agent(
    profile: ProfileSpec,
    resolved: ResolvedModel,
    tools: Sequence[BaseTool],
    backend: BackendProtocol,
    checkpointer: BaseCheckpointSaver | None,
    store: BaseStore | None,
    subagent_model: BaseChatModel | None = None,
    middleware_extra: Sequence[Any] = (),
):
    """Compila el agente del perfil con `create_deep_agent`.

    `tools` es el conjunto de herramientas del perfil (`tools.get_tools`); cada agente recibe
    solo las que nombra su configuración. `subagent_model` (si se da) sustituye al modelo
    principal en los subagentes; sin él, los subagentes usan el modelo del run y su failover.
    """
    config = profile.config
    main_model = resolved.chat_model
    planning = bool(config.get("planning"))

    main_middleware: list[Any] = []
    if planning:
        main_middleware.append(TodoListMiddleware())
    main_middleware.append(SourcesMiddleware())
    # RAG: solo si el perfil puede buscar en la documentación (sin embeddings configurados no hace nada).
    if "search_team_docs" in config.get("tools", []):
        # La búsqueda web previa solo si el agente puede buscar en la web (hay clave de Tavily) y
        # responde él solo: con subagentes (research) el plan decide qué buscar.
        has_web = "web_search" in config.get("tools", []) and any(
            getattr(tool, "name", None) == "web_search" for tool in tools
        )
        main_middleware.append(
            GroundingMiddleware(
                web_fallback=has_web and not config.get("subagents"),
                max_searches=int((config.get("limits") or {}).get("max_searches", 3)),
            )
        )
    max_subagents = (config.get("limits") or {}).get("max_subagents")
    if config.get("subagents") and max_subagents is not None:
        main_middleware.append(SubagentLimitMiddleware(int(max_subagents)))
    main_middleware.extend(_fallback_middleware(resolved.fallback_models))
    main_middleware.extend(middleware_extra)

    use_main_for_subagents = subagent_model is None
    sub_model = subagent_model or main_model
    sub_fallbacks = resolved.fallback_models if use_main_for_subagents else ()
    subagents = [
        _subagent_spec(spec, tools, sub_model, sub_fallbacks) for spec in config.get("subagents", [])
    ]

    interrupt_on: dict[str, Any] | None = None
    if planning and config.get("plan_review"):
        interrupt_on = {
            "write_todos": {
                "allowed_decisions": ["approve", "edit", "reject"],
                "when": _first_plan_only,
            }
        }

    _disable_general_purpose_subagent(main_model)
    return create_deep_agent(
        model=main_model,
        tools=_select_tools(tools, config.get("tools", [])),
        system_prompt=profile.system_prompt,
        middleware=main_middleware,
        subagents=subagents or None,
        # Permisos de solo lectura para el agente principal y, por herencia, para todos los subagentes.
        permissions=READ_ONLY_PERMISSIONS,
        backend=backend,
        interrupt_on=interrupt_on,
        checkpointer=checkpointer,
        store=store,
        context_schema=SofeeContext,
        name=f"sofee-{profile.mode}",
    )


__all__ = [
    "DEFAULT_PROFILES",
    "MODES",
    "ProfileSpec",
    "build_agent",
    "load_profile",
]
