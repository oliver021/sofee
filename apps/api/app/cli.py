import asyncio
import argparse
import getpass
import uuid

from sqlalchemy import select

from .agent.persistence import setup_agent_storage
from .core.security import hash_password
from .db import async_session_factory
from .demo_seed import DemoSeedError, DemoSeedResult, run_seed_demo
from .models.catalog import ModelCatalogBinding, ModelCatalogEntry
from .models.provider import Provider, ProviderKind, ProviderModel
from .models.user import User, UserRole
from .services.embeddings import EmbeddingsError, embeddings_enabled
from .services.providers import create_credential, get_active_credential
from .services.rag import reindex_all


async def _create_admin(email: str, password: str, display_name: str) -> User:
    async with async_session_factory() as db:
        existing = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if existing is not None:
            raise SystemExit(f"User {email} already exists")
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name or email.split("@")[0],
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _get_or_create_user(
    db, email: str, password: str, display_name: str, role: UserRole
) -> User:
    existing = (
        await db.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        display_name=display_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _get_or_create_provider(
    db,
    *,
    name: str,
    kind: ProviderKind,
    base_url: str | None,
    api_key: str,
    actor_id,
    models: list[tuple[str, str]],
) -> Provider:
    existing = (
        await db.execute(select(Provider).where(Provider.name == name))
    ).scalar_one_or_none()
    provider = existing
    if provider is None:
        provider = Provider(
            name=name, kind=kind, base_url=base_url, is_enabled=True, created_by=actor_id
        )
        db.add(provider)
        await db.flush()

    if await get_active_credential(db, provider.id) is None:
        await create_credential(db, provider.id, api_key, actor_id)

    existing_model_ids = {
        m.model_id
        for m in (
            await db.execute(
                select(ProviderModel).where(ProviderModel.provider_id == provider.id)
            )
        ).scalars()
    }
    for model_id, display_name in models:
        if model_id in existing_model_ids:
            continue
        db.add(
            ProviderModel(
                provider_id=provider.id,
                model_id=model_id,
                display_name=display_name,
                is_enabled=True,
            )
        )
    return provider


async def _get_or_create_catalog_entry(
    db,
    *,
    slug: str,
    display_name: str,
    category: str,
    actor_id,
    bindings: list[tuple[uuid.UUID, str]],
) -> None:
    """`bindings` es una lista ordenada de (provider_id, model_id): la primera es primaria."""
    entry = (
        await db.execute(select(ModelCatalogEntry).where(ModelCatalogEntry.slug == slug))
    ).scalar_one_or_none()
    if entry is None:
        entry = ModelCatalogEntry(
            slug=slug, display_name=display_name, category=category, created_by=actor_id
        )
        db.add(entry)
        await db.flush()

    existing_model_ids = {
        b.provider_model_id
        for b in (
            await db.execute(
                select(ModelCatalogBinding).where(ModelCatalogBinding.catalog_entry_id == entry.id)
            )
        ).scalars()
    }
    for priority, (provider_id, model_id) in enumerate(bindings):
        model = (
            await db.execute(
                select(ProviderModel).where(
                    ProviderModel.provider_id == provider_id, ProviderModel.model_id == model_id
                )
            )
        ).scalar_one_or_none()
        if model is None or model.id in existing_model_ids:
            continue
        db.add(
            ModelCatalogBinding(catalog_entry_id=entry.id, provider_model_id=model.id, priority=priority)
        )


async def _seed_dev() -> None:
    """Datos de prueba para revisar el proyecto e2e. NO usar en producción."""
    admin_password = "AdminSeed123!"
    user_password = "UserSeed123!"

    async with async_session_factory() as db:
        admin = await _get_or_create_user(
            db, "admin@sofee.dev", admin_password, "Admin (seed)", UserRole.admin
        )
        await _get_or_create_user(
            db, "user@sofee.dev", user_password, "Usuario (seed)", UserRole.regular
        )
        await db.flush()

        deepinfra = await _get_or_create_provider(
            db,
            name="DeepInfra (seed)",
            kind=ProviderKind.deepinfra,
            base_url=None,
            api_key="sk-seed-deepinfra-0000000000000000",
            actor_id=admin.id,
            models=[
                ("meta-llama/Meta-Llama-3.1-8B-Instruct", "Llama 3.1 8B Instruct"),
                ("mistralai/Mixtral-8x7B-Instruct-v0.1", "Mixtral 8x7B Instruct"),
            ],
        )
        local = await _get_or_create_provider(
            db,
            name="Local OpenAI-compatible (seed)",
            kind=ProviderKind.openai_compatible,
            base_url="http://localhost:11434/v1",
            api_key="sk-seed-local-0000000000000000",
            actor_id=admin.id,
            models=[("llama3.1:8b", "Llama 3.1 8B (local)")],
        )
        await db.flush()

        await _get_or_create_catalog_entry(
            db,
            slug="fast",
            display_name="Rápido",
            category="rapido",
            actor_id=admin.id,
            bindings=[
                (deepinfra.id, "meta-llama/Meta-Llama-3.1-8B-Instruct"),
                (local.id, "llama3.1:8b"),
            ],
        )
        await _get_or_create_catalog_entry(
            db,
            slug="balanced",
            display_name="Balanceado",
            category="balanceado",
            actor_id=admin.id,
            bindings=[(deepinfra.id, "mistralai/Mixtral-8x7B-Instruct-v0.1")],
        )

        await db.commit()

    print("Seed de desarrollo listo:")
    print(f"  admin  -> admin@sofee.dev / {admin_password}")
    print(f"  regular-> user@sofee.dev / {user_password}")
    print("  providers: 'DeepInfra (seed)', 'Local OpenAI-compatible (seed)'")
    print("  catálogo: 'Rápido' (con fallback), 'Balanceado'")
    print("Las API keys son ficticias: 'Probar conexión' fallará hasta rotar la credencial.")


def _print_demo_summary(result: DemoSeedResult) -> None:
    print("Demo lista:")
    print(f"  documentos de la base de conocimiento: {result.kb_documents}")
    if result.kb_chunks:
        print(f"  trozos indexados para RAG: {result.kb_chunks}")
    if result.profiles_created:
        print(f"  perfiles creados (versión 1): {', '.join(result.profiles_created)}")
    if result.starters_set:
        print("  preguntas de arranque: creadas (en y es, por modo)")
    if result.tavily_configured:
        print("  Tavily: clave configurada")
    if result.catalog_slug:
        print(f"  catálogo: '{result.catalog_slug}' (Sofee Pro)")
        for model_id, verdict in result.probes.items():
            print(f"    {model_id}: prueba de herramientas -> {verdict}")
    for email, password in result.generated_passwords.items():
        print(f"  {email} -> contraseña generada: {password}")
        print("    (se muestra una sola vez; cámbiala o guárdala ahora)")
    for note in result.notes:
        print(f"  aviso: {note}")


async def _reindex_kb() -> tuple[int, int]:
    if not embeddings_enabled():
        raise EmbeddingsError("Configura EMBEDDINGS_BASE_URL y EMBEDDINGS_MODEL")
    async with async_session_factory() as db:
        counts = await reindex_all(db)
        await db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Sofee API admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create_user = sub.add_parser("create-admin", help="Crear el primer usuario admin")
    create_user.add_argument("--email", required=True)
    create_user.add_argument("--password")
    create_user.add_argument("--display-name")
    create_user.set_defaults(command="create_admin")

    sub.add_parser(
        "seed-dev",
        help="Poblar usuarios y providers de prueba para revisión e2e (solo desarrollo)",
    ).set_defaults(command="seed_dev")

    sub.add_parser(
        "setup-agent-storage",
        help="Crear las tablas del checkpointer y del store del agente (paso migrate del release)",
    ).set_defaults(command="setup_agent_storage")

    sub.add_parser(
        "seed-demo",
        help="Sembrar la demo: usuarios, base de conocimiento, perfiles y preguntas (idempotente)",
    ).set_defaults(command="seed_demo")

    sub.add_parser(
        "reindex-kb",
        help="Recalcular los embeddings de la base de conocimiento (RAG); tras cambiar de modelo",
    ).set_defaults(command="reindex_kb")

    args = parser.parse_args()

    if args.command == "create_admin":
        password = args.password or getpass.getpass("Password: ")
        user = asyncio.run(_create_admin(args.email, password, args.display_name))
        print(f"Admin created: {user.email} (id={user.id})")
    elif args.command == "seed_dev":
        asyncio.run(_seed_dev())
    elif args.command == "setup_agent_storage":
        asyncio.run(setup_agent_storage())
        print("Agent storage listo (checkpointer y store).")
    elif args.command == "reindex_kb":
        try:
            documents, chunks = asyncio.run(_reindex_kb())
        except EmbeddingsError as exc:
            raise SystemExit(f"reindex-kb: {exc}") from exc
        print(f"Reindexado: {documents} documentos, {chunks} trozos.")
    elif args.command == "seed_demo":
        try:
            result = asyncio.run(run_seed_demo())
        except DemoSeedError as exc:
            raise SystemExit(f"seed-demo: {exc}") from exc
        _print_demo_summary(result)


if __name__ == "__main__":
    main()