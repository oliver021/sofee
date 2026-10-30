"""Datos de prueba para el admin del agente: hilos, runs con eventos, providers y catálogo.

Todo se escribe con el ORM directamente, sin pasar por el executor, así que los runs tienen las
fechas, tokens y estados exactos que cada prueba necesita.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.db import async_session_factory
from app.models.agent import AgentRun, AgentRunEvent
from app.models.catalog import ModelCatalogBinding, ModelCatalogEntry
from app.models.provider import Provider, ProviderKind, ProviderModel
from app.models.thread import Message, Thread
from app.models.user import User
from app.services.providers import create_credential


async def make_thread(owner: User, client_id: str = "thread-abc", mode: str = "learn") -> Thread:
    async with async_session_factory() as db:
        thread = Thread(owner_id=owner.id, client_id=client_id, mode=mode, title="Hilo de prueba")
        db.add(thread)
        await db.commit()
        await db.refresh(thread)
        return thread


async def make_run(
    thread: Thread,
    user: User,
    *,
    question: str = "¿Qué es un servicio?",
    answer: str = "Un servicio es un programa que atiende peticiones.",
    mode: str = "learn",
    status: str = "completed",
    created_at: datetime | None = None,
    duration: timedelta | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: Decimal | None = None,
    ttft_ms: int | None = None,
    catalog_slug: str | None = None,
    model_label: str | None = None,
    provider_model_id: uuid.UUID | None = None,
    hallucinated: int = 0,
    error_code: str | None = None,
    events: list[tuple[str, dict[str, Any]]] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> AgentRun:
    """Un par de mensajes (pregunta y respuesta) con su run y sus eventos. Las fechas son explícitas."""
    created = created_at or datetime.now(UTC)
    assistant_status = {"completed": "complete", "cancelled": "stopped", "failed": "error"}.get(status, "pending")
    async with async_session_factory() as db:
        question_row = Message(
            thread_id=thread.id,
            client_id=f"u-{uuid.uuid4()}",
            role="user",
            text=question,
            status="complete",
        )
        db.add(question_row)
        await db.flush()
        answer_row = Message(
            thread_id=thread.id,
            client_id=f"a-{uuid.uuid4()}",
            role="assistant",
            text=answer,
            status=assistant_status,
            citations=citations,
        )
        db.add(answer_row)
        await db.flush()
        run = AgentRun(
            thread_id=thread.id,
            user_id=user.id,
            user_message_id=question_row.id,
            assistant_message_id=answer_row.id,
            kind="send",
            mode=mode,
            catalog_slug=catalog_slug,
            model_label=model_label,
            provider_model_id=provider_model_id,
            status=status,
            error_code=error_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost,
            ttft_ms=ttft_ms,
            hallucinated_citations=hallucinated,
            created_at=created,
            started_at=created,
            finished_at=created + duration if duration is not None else None,
        )
        db.add(run)
        await db.flush()
        for seq, (kind, payload) in enumerate(events or [], start=1):
            db.add(AgentRunEvent(run_id=run.id, seq=seq, type=kind, payload=payload))
        await db.commit()
        await db.refresh(run)
        return run


async def make_answer_feedback(
    run: AgentRun, user: User, *, value: str = "bad", reason: str | None = "incorrecta", comment: str | None = None
):
    from app.models.feedback import MessageFeedback

    async with async_session_factory() as db:
        feedback = MessageFeedback(
            message_id=run.assistant_message_id,
            user_id=user.id,
            value=value,
            reason=reason,
            comment=comment,
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        return feedback


async def make_provider(
    name: str = "DeepInfra",
    *,
    kind: ProviderKind = ProviderKind.deepinfra,
    base_url: str | None = None,
    api_key: str | None = "sk-test-proveedor-1234",
    enabled: bool = True,
) -> Provider:
    async with async_session_factory() as db:
        provider = Provider(name=name, kind=kind, base_url=base_url, is_enabled=enabled)
        db.add(provider)
        await db.flush()
        if api_key:
            await create_credential(db, provider.id, api_key, None)
        await db.commit()
        await db.refresh(provider)
        return provider


async def make_model(
    provider: Provider,
    model_id: str = "modelo-a",
    *,
    supports_tools: bool | None = None,
    context_window: int | None = None,
    input_price: Decimal | None = None,
    output_price: Decimal | None = None,
    enabled: bool = True,
) -> ProviderModel:
    async with async_session_factory() as db:
        model = ProviderModel(
            provider_id=provider.id,
            model_id=model_id,
            display_name=model_id,
            is_enabled=enabled,
            supports_tools=supports_tools,
            context_window=context_window,
            input_price_per_mtok=input_price,
            output_price_per_mtok=output_price,
        )
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model


async def make_entry(slug: str, models: list[ProviderModel], *, enabled: bool = True) -> ModelCatalogEntry:
    async with async_session_factory() as db:
        entry = ModelCatalogEntry(
            slug=slug,
            display_name=f"Modelo {slug}",
            category="agente",
            is_enabled=enabled,
            sort_order=0,
        )
        db.add(entry)
        await db.flush()
        for priority, model in enumerate(models):
            db.add(
                ModelCatalogBinding(
                    catalog_entry_id=entry.id,
                    provider_model_id=model.id,
                    priority=priority,
                )
            )
        await db.commit()
        await db.refresh(entry)
        return entry


async def fetch_model(model_id: uuid.UUID) -> ProviderModel:
    async with async_session_factory() as db:
        return await db.get(ProviderModel, model_id)


__all__ = [
    "fetch_model",
    "make_answer_feedback",
    "make_entry",
    "make_model",
    "make_provider",
    "make_run",
    "make_thread",
]
