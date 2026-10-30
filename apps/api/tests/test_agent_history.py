"""Historial de entrada del modelo y entrada de Compactar, leídos de la tabla `messages`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.history import (
    CONTINUE_INSTRUCTION,
    SUMMARY_HEADER,
    load_compaction_input,
    load_model_input,
    summary_request,
)
from app.db import async_session_factory
from app.models.thread import Message, Thread
from tests.helpers import create_user


async def _thread_with(
    db: AsyncSession, rows: list[tuple[str, str, str]], *, email: str = "historial@example.com"
) -> tuple[Thread, dict[str, Message]]:
    """Hilo `thread-h` con mensajes (client_id, role, status), en ese orden.

    El texto es `text-<client_id>`. Status `empty` crea un mensaje completo sin texto útil.
    """
    user = await create_user(email=email)
    thread = Thread(owner_id=user.id, client_id="thread-h", mode="learn")
    db.add(thread)
    await db.flush()
    messages: dict[str, Message] = {}
    for client_id, role, status in rows:
        message = Message(
            thread_id=thread.id,
            client_id=client_id,
            role=role,
            text="   " if status == "empty" else f"text-{client_id}",
            status="complete" if status == "empty" else status,
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)  # carga el seq que asigna la secuencia
        messages[client_id] = message
    await db.commit()
    await db.refresh(thread)
    return thread, messages


async def _model_input(user_client_id: str, **kwargs) -> list[str]:
    async with async_session_factory() as db:
        thread = (await db.execute(select(Thread).where(Thread.client_id == "thread-h"))).scalar_one()
        user_message = (
            await db.execute(
                select(Message).where(Message.thread_id == thread.id, Message.client_id == user_client_id)
            )
        ).scalar_one()
        messages = await load_model_input(db, thread, user_message, **kwargs)
    return [f"{m.type}:{m.content}" for m in messages]


async def test_only_complete_or_stopped_user_and_assistant_text_before_the_current_turn():
    async with async_session_factory() as db:
        await _thread_with(
            db,
            [
                ("u1", "user", "complete"),
                ("a1", "assistant", "complete"),
                ("a-err", "assistant", "error"),
                ("u2", "user", "complete"),
                ("a2", "assistant", "stopped"),
                ("a-empty", "assistant", "empty"),
                ("a-pend", "assistant", "pending"),
                ("u3", "user", "complete"),
                ("a3", "assistant", "complete"),
            ],
        )
    assert await _model_input("u3") == [
        "human:text-u1",
        "ai:text-a1",
        "human:text-u2",
        "ai:text-a2",
        "human:text-u3",
    ]


async def test_continue_appends_the_partial_answer_and_the_instruction():
    async with async_session_factory() as db:
        await _thread_with(db, [("u1", "user", "complete"), ("a1", "assistant", "stopped")])
    assert await _model_input("u1", continue_text="parcial") == [
        "human:text-u1",
        "ai:parcial",
        f"human:{CONTINUE_INSTRUCTION}",
    ]


async def test_clear_cut_drops_older_turns_and_a_summary_from_before_it():
    async with async_session_factory() as db:
        thread, messages = await _thread_with(
            db,
            [
                ("u1", "user", "complete"),
                ("a1", "assistant", "complete"),
                ("u2", "user", "complete"),
                ("a2", "assistant", "complete"),
                ("u3", "user", "complete"),
            ],
        )
        thread.context_start_seq = messages["u2"].seq
        thread.summary = "resumen viejo"
        thread.summary_through_seq = messages["a1"].seq
        await db.commit()
    assert await _model_input("u3") == ["human:text-u2", "ai:text-a2", "human:text-u3"]


async def test_summary_replaces_the_turns_it_covers():
    async with async_session_factory() as db:
        thread, messages = await _thread_with(
            db,
            [
                ("u1", "user", "complete"),
                ("a1", "assistant", "complete"),
                ("u2", "user", "complete"),
                ("a2", "assistant", "complete"),
                ("u3", "user", "complete"),
            ],
        )
        thread.summary = "resumen"
        thread.summary_through_seq = messages["a1"].seq
        await db.commit()
    got = await _model_input("u3")
    assert got[0] == f"human:{SUMMARY_HEADER}\nresumen"
    assert got[1:] == ["human:text-u2", "ai:text-a2", "human:text-u3"]


async def test_compaction_input_takes_only_the_turns_after_the_previous_cut():
    async with async_session_factory() as db:
        thread, messages = await _thread_with(
            db,
            [
                ("u1", "user", "complete"),
                ("a1", "assistant", "complete"),
                ("u2", "user", "complete"),
                ("a2", "assistant", "stopped"),
            ],
        )
        thread.summary = "previo"
        thread.summary_through_seq = messages["a1"].seq
        await db.commit()
        compaction = await load_compaction_input(db, thread)

    assert compaction.previous_summary == "previo"
    assert [turn.text for turn in compaction.turns] == ["text-u2", "text-a2"]
    assert compaction.through_seq == messages["a2"].seq
    system, human = summary_request(compaction)
    assert system.type == "system"
    assert human.content.startswith("Resumen previo:\nprevio")
    assert "Usuario: text-u2" in human.content and "Asistente: text-a2" in human.content


async def test_compaction_without_new_turns_has_nothing_to_summarise():
    async with async_session_factory() as db:
        thread, messages = await _thread_with(db, [("u1", "user", "complete"), ("a1", "assistant", "complete")])
        thread.summary = "ya resumido"
        thread.summary_through_seq = messages["a1"].seq
        await db.commit()
        compaction = await load_compaction_input(db, thread)
    assert compaction.turns == () or list(compaction.turns) == []
    assert compaction.through_seq is None
