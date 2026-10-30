"""Datos de la demo: `python -m app.cli seed-demo` (roadmap F6).

Idempotente: cada paso comprueba si ya está hecho y no pisa lo que el admin haya cambiado.
- Usuarios de la demo (admin y regular). Si `SOFEE_DEMO_ADMIN_PASSWORD` o
  `SOFEE_DEMO_USER_PASSWORD` no están, la contraseña se genera y se devuelve una sola vez.
- Base de conocimiento desde `demo/kb/*.md`, con el mismo servicio que el admin: `kb_documents`
  y su copia en el store, que es lo que lee el agente en `/kb/`.
- Versión 1 de cada perfil de agente, tomada de los defaults de código.
- Preguntas de arranque por modo e idioma, si el ajuste `starters` no existe.
- Proveedor, entrada de catálogo `pro` ("Sofee Pro") y su aptitud para agentes, solo si
  `SOFEE_DEMO_PROVIDER_KIND` está definido. Las capacidades las fija la prueba real de herramientas.
- Clave de Tavily, si `SOFEE_DEMO_TAVILY_API_KEY` está definida.

Ningún secreto sale del entorno ni se escribe en el repositorio.
"""

import os
import secrets
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from langgraph.store.base import BaseStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent.knowledge import mirror_document, unmirror_document
from .agent.persistence import close_agent_storage, open_agent_storage
from .agent.probe import (
    NO_TOOL_CALL,
    REJECTED,
    SUPPORTS,
    ProbeResult,
    probe_tool_calling,
)
from .agent.profiles import DEFAULT_PROFILES, MODES
from .core.security import hash_password
from .db import async_session_factory
from .models.agent import AgentProfile
from .models.app_setting import AppSetting
from .models.catalog import ModelCatalogBinding, ModelCatalogEntry
from .models.kb import KbDocument
from .models.provider import Provider, ProviderKind, ProviderModel
from .models.user import User, UserRole
from .services.agent_config import create_version, validate_profile_config
from .services.extraction import CONTENT_TYPES, extract_text
from .services.integrations import TAVILY, is_configured, store_credential
from .services.knowledge import kb_path, slugify, title_for, unique_slug
from .services.providers import create_credential, get_active_credential

DEMO_KB_DIR = Path(__file__).resolve().parents[1] / "demo" / "kb"
ADMIN_EMAIL = "admin@sofee.demo"
USER_EMAIL = "usuario@sofee.demo"
PROVIDER_NAME = "Proveedor de la demo"
CATALOG_SLUG = "pro"
CATALOG_NAME = "Sofee Pro"
CATALOG_CATEGORY = "avanzado"
DEFAULT_CONTEXT_WINDOW = 128_000
_STARTERS_KEY = "starters"

DEMO_STARTERS: dict[str, dict[str, list[str]]] = {
    "learn": {
        "es": [
            "¿Cómo se despliega un servicio aquí?",
            "¿Qué hace el servicio de cuentas y cómo se entra en él?",
            "¿Qué significa estar de guardia y qué se espera de mí?",
        ],
        "en": [
            "How do we deploy a service here?",
            "What does the accounts service do, and how do you sign in to it?",
            "What does being on call mean, and what is expected of me?",
        ],
    },
    "research": {
        "es": [
            "¿Deberíamos cambiar la cola de eventos por otra tecnología?",
            "¿Qué enseñó el incidente de la cola de eventos y qué falta por hacer?",
            "¿Cómo medimos la latencia de pedidos antes de optimizarla?",
        ],
        "en": [
            "Should we replace the event queue with a different technology?",
            "What did the event queue incident teach us, and what is still open?",
            "How should we measure order latency before we optimise it?",
        ],
    },
    "explore": {
        "es": [
            "¿Qué debo saber de la plataforma de datos?",
            "¿Cómo funciona una revisión de código en el equipo?",
            "¿Qué decisiones de arquitectura se han tomado y por qué?",
        ],
        "en": [
            "What should I know about the data platform?",
            "How does a code review work on this team?",
            "Which architecture decisions have we made, and why?",
        ],
    },
}

ProbeFn = Callable[..., Awaitable[ProbeResult]]


class DemoSeedError(Exception):
    """La configuración de la demo no es válida. El mensaje no contiene secretos."""


@dataclass
class DemoSeedResult:
    # Solo las contraseñas generadas en esta pasada (email -> contraseña). Vacío si vinieron del entorno.
    generated_passwords: dict[str, str] = field(default_factory=dict)
    kb_documents: int = 0
    profiles_created: list[str] = field(default_factory=list)
    starters_set: bool = False
    tavily_configured: bool = False
    catalog_slug: str | None = None
    # model_id -> veredicto de la prueba de herramientas ("supports", "inconclusive"...).
    probes: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ProviderSettings:
    kind: ProviderKind
    api_key: str
    base_url: str | None
    main_model: str
    worker_model: str | None
    context_window: int


async def run_seed_demo() -> DemoSeedResult:
    """Lo que ejecuta la CLI: abre el almacenamiento del agente (Postgres) y siembra la demo."""
    storage = await open_agent_storage()
    try:
        return await seed_demo(storage.store)
    finally:
        await close_agent_storage(storage)


async def seed_demo(
    store: BaseStore,
    *,
    env: Mapping[str, str] | None = None,
    probe: ProbeFn = probe_tool_calling,
) -> DemoSeedResult:
    """Siembra la demo. `env` y `probe` se inyectan en los tests; por defecto son el entorno real."""
    environment = os.environ if env is None else env
    provider = _provider_settings(environment)
    tavily_key = _env_value(environment, "SOFEE_DEMO_TAVILY_API_KEY")
    documents = _demo_documents()

    result = DemoSeedResult(kb_documents=len(documents))
    if provider is None:
        result.notes.append(
            "Sin SOFEE_DEMO_PROVIDER_KIND: no se crea proveedor ni 'Sofee Pro'. "
            "Sin proveedor, el agente solo responde con runs grabados (replay.map)."
        )

    async with async_session_factory() as db:
        admin = await _demo_user(
            db, ADMIN_EMAIL, "Admin (demo)", UserRole.admin, "SOFEE_DEMO_ADMIN_PASSWORD", environment, result
        )
        await _demo_user(
            db, USER_EMAIL, "Usuario (demo)", UserRole.regular, "SOFEE_DEMO_USER_PASSWORD", environment, result
        )
        documents_rows = await _load_documents(db, documents, admin.id)
        await _default_profiles(db, admin.id, result)
        await _starters(db, result)
        if tavily_key is not None:
            await _tavily(db, tavily_key, admin.id, result)
        if provider is not None:
            await _provider_and_catalog(db, provider, admin.id, probe, result)
        await db.commit()

        # Después del commit, como en el admin: la copia del store nunca va por delante de la BD.
        for document in documents_rows:
            await db.refresh(document)
            if document.is_enabled:
                await mirror_document(store, document)
            else:
                await unmirror_document(store, document.slug)
    return result


def _env_value(environment: Mapping[str, str], name: str) -> str | None:
    value = (environment.get(name) or "").strip()
    return value or None


def _provider_settings(environment: Mapping[str, str]) -> _ProviderSettings | None:
    kind_name = _env_value(environment, "SOFEE_DEMO_PROVIDER_KIND")
    if kind_name is None:
        return None
    try:
        kind = ProviderKind(kind_name)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in ProviderKind)
        raise DemoSeedError(f"SOFEE_DEMO_PROVIDER_KIND no es válido. Valores: {allowed}") from exc
    api_key = _env_value(environment, "SOFEE_DEMO_API_KEY")
    if api_key is None:
        raise DemoSeedError("Falta SOFEE_DEMO_API_KEY (la key del provider de la demo).")
    main_model = _env_value(environment, "SOFEE_DEMO_MAIN_MODEL")
    if main_model is None:
        raise DemoSeedError("Falta SOFEE_DEMO_MAIN_MODEL (el modelo principal de Sofee Pro).")
    base_url = _env_value(environment, "SOFEE_DEMO_BASE_URL")
    if kind is ProviderKind.openai_compatible and base_url is None:
        raise DemoSeedError("SOFEE_DEMO_BASE_URL es obligatoria con un provider openai_compatible.")
    return _ProviderSettings(
        kind=kind,
        api_key=api_key,
        base_url=base_url,
        main_model=main_model,
        worker_model=_env_value(environment, "SOFEE_DEMO_WORKER_MODEL"),
        context_window=_context_window(environment),
    )


def _context_window(environment: Mapping[str, str]) -> int:
    raw = _env_value(environment, "SOFEE_DEMO_CONTEXT_WINDOW")
    if raw is None:
        return DEFAULT_CONTEXT_WINDOW
    if not raw.isdigit() or int(raw) <= 0:
        raise DemoSeedError("SOFEE_DEMO_CONTEXT_WINDOW debe ser un entero positivo.")
    return int(raw)


def _demo_documents() -> list[tuple[str, bytes]]:
    paths = sorted(DEMO_KB_DIR.glob("*.md"))
    if not paths:
        raise DemoSeedError(f"No hay documentos de demo en {DEMO_KB_DIR}")
    return [(path.name, path.read_bytes()) for path in paths]


async def _demo_user(
    db: AsyncSession,
    email: str,
    display_name: str,
    role: UserRole,
    password_env: str,
    environment: Mapping[str, str],
    result: DemoSeedResult,
) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        return existing
    configured = _env_value(environment, password_env)
    password = configured or secrets.token_urlsafe(16)
    if configured is None:
        result.generated_passwords[email] = password
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _load_documents(
    db: AsyncSession, files: list[tuple[str, bytes]], actor_id: uuid.UUID
) -> list[KbDocument]:
    """Crea o actualiza cada documento. Un documento ya subido se reconoce por su nombre de archivo."""
    loaded: list[KbDocument] = []
    for filename, data in files:
        text = extract_text(filename, data)
        document = (
            await db.execute(select(KbDocument).where(KbDocument.source_filename == filename))
        ).scalar_one_or_none()
        if document is None:
            slug = await unique_slug(db, slugify(PurePosixPath(filename).stem), set())
            document = KbDocument(
                slug=slug,
                title=title_for(filename, text),
                path=kb_path(slug),
                source_filename=filename,
                content_type=CONTENT_TYPES[".md"],
                text=text,
                tags=[],
                is_enabled=True,
                size_bytes=len(data),
                created_by=actor_id,
            )
            db.add(document)
        else:
            # Se respeta si el admin lo retiró (`is_enabled`); el texto sí vuelve al del archivo.
            document.title = title_for(filename, text)
            document.text = text
            document.size_bytes = len(data)
        loaded.append(document)
    await db.flush()
    return loaded


async def _default_profiles(db: AsyncSession, actor_id: uuid.UUID, result: DemoSeedResult) -> None:
    for mode in MODES:
        has_version = (
            await db.execute(select(AgentProfile.id).where(AgentProfile.mode == mode).limit(1))
        ).first()
        if has_version is not None:
            continue
        await create_version(
            db,
            mode,
            system_prompt=DEFAULT_PROFILES[mode]["system_prompt"],
            config=validate_profile_config(mode, {}),
            actor_id=actor_id,
        )
        result.profiles_created.append(mode)


async def _starters(db: AsyncSession, result: DemoSeedResult) -> None:
    if await db.get(AppSetting, _STARTERS_KEY) is not None:
        return
    db.add(AppSetting(key=_STARTERS_KEY, value=DEMO_STARTERS))
    result.starters_set = True


async def _tavily(db: AsyncSession, key: str, actor_id: uuid.UUID, result: DemoSeedResult) -> None:
    # Una clave ya activa no se reemplaza: rotarla es una acción del admin, con su auditoría.
    if not await is_configured(db, TAVILY):
        await store_credential(db, TAVILY, key, actor_id)
    result.tavily_configured = True


async def _provider_and_catalog(
    db: AsyncSession,
    settings: _ProviderSettings,
    actor_id: uuid.UUID,
    probe: ProbeFn,
    result: DemoSeedResult,
) -> None:
    provider = (
        await db.execute(select(Provider).where(Provider.name == PROVIDER_NAME))
    ).scalar_one_or_none()
    if provider is None:
        provider = Provider(
            name=PROVIDER_NAME,
            kind=settings.kind,
            base_url=settings.base_url,
            is_enabled=True,
            created_by=actor_id,
        )
        db.add(provider)
        await db.flush()
    if await get_active_credential(db, provider.id) is None:
        await create_credential(db, provider.id, settings.api_key, actor_id)

    models = [await _provider_model(db, provider, settings.main_model, settings.context_window)]
    if settings.worker_model is not None:
        models.append(await _provider_model(db, provider, settings.worker_model, settings.context_window))

    entry = (
        await db.execute(select(ModelCatalogEntry).where(ModelCatalogEntry.slug == CATALOG_SLUG))
    ).scalar_one_or_none()
    if entry is None:
        entry = ModelCatalogEntry(
            slug=CATALOG_SLUG,
            display_name=CATALOG_NAME,
            description="Modelo principal de la demo, con respaldo.",
            category=CATALOG_CATEGORY,
            is_enabled=True,
            sort_order=0,
            created_by=actor_id,
        )
        db.add(entry)
        await db.flush()
    bound = set(
        (
            await db.execute(
                select(ModelCatalogBinding.provider_model_id).where(
                    ModelCatalogBinding.catalog_entry_id == entry.id
                )
            )
        ).scalars()
    )
    for priority, model in enumerate(models):
        if model.id not in bound:
            db.add(ModelCatalogBinding(catalog_entry_id=entry.id, provider_model_id=model.id, priority=priority))
    await db.flush()

    # `supports_tools` lo fija una llamada real, como en "Probar como agente": nunca a mano.
    for model in models:
        if model.supports_tools is None:
            outcome = await probe(provider, model, settings.api_key)
            if outcome.verdict == SUPPORTS:
                model.supports_tools = True
            elif outcome.verdict in (NO_TOOL_CALL, REJECTED):
                model.supports_tools = False
            result.probes[model.model_id] = outcome.verdict
        else:
            result.probes[model.model_id] = "already_verified"
    result.catalog_slug = CATALOG_SLUG


async def _provider_model(
    db: AsyncSession, provider: Provider, model_id: str, context_window: int
) -> ProviderModel:
    model = (
        await db.execute(
            select(ProviderModel).where(
                ProviderModel.provider_id == provider.id, ProviderModel.model_id == model_id
            )
        )
    ).scalar_one_or_none()
    if model is None:
        model = ProviderModel(
            provider_id=provider.id,
            model_id=model_id,
            display_name=model_id,
            is_enabled=True,
            context_window=context_window,
        )
        db.add(model)
        await db.flush()
    return model


__all__ = [
    "ADMIN_EMAIL",
    "CATALOG_SLUG",
    "DEMO_KB_DIR",
    "DEMO_STARTERS",
    "USER_EMAIL",
    "DemoSeedError",
    "DemoSeedResult",
    "run_seed_demo",
    "seed_demo",
]
