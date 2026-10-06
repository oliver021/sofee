from datetime import UTC, datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.thread import Message, Thread
from ...schemas import (
    MessageCreate,
    MessageOut,
    ThreadCreate,
    ThreadDetail,
    ThreadOut,
    ThreadUpdate,
)
from ..deps import AuthContext, check_csrf, get_current_auth

router = APIRouter(tags=["conversations"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.client_id,
        role=message.role,  # type: ignore[arg-type]
        text=message.text,
        status=message.status,  # type: ignore[arg-type]
        citations=message.citations,
        attachment_ids=message.attachment_ids or [],
        seq=message.seq,
        created_at=message.created_at,
    )


async def _owned_thread(
    db: AsyncSession, owner_id: uuid.UUID, client_id: str
) -> Thread:
    thread = (
        await db.execute(
            select(Thread).where(
                Thread.owner_id == owner_id, Thread.client_id == client_id
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise _not_found()
    return thread


async def _thread_out(db: AsyncSession, thread: Thread, *, count: bool = True) -> ThreadOut:
    message_count = 0
    if count:
        message_count = (
            await db.execute(
                select(func.count(Message.id)).where(Message.thread_id == thread.id)
            )
        ).scalar_one()
    return ThreadOut(
        id=thread.client_id,
        title=thread.title,
        mode=thread.mode,  # type: ignore[arg-type]
        message_count=message_count,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> list[ThreadOut]:
    rows = await db.execute(
        select(Thread, func.count(Message.id))
        .outerjoin(Message, Message.thread_id == Thread.id)
        .where(Thread.owner_id == auth.user.id)
        .group_by(Thread.id)
        .order_by(Thread.updated_at.desc())
    )
    return [
        ThreadOut(
            id=thread.client_id,
            title=thread.title,
            mode=thread.mode,  # type: ignore[arg-type]
            message_count=count,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
        )
        for thread, count in rows.all()
    ]


@router.post("/threads", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
async def upsert_thread(
    payload: ThreadCreate,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ThreadOut:
    thread = (
        await db.execute(
            select(Thread).where(
                Thread.owner_id == auth.user.id, Thread.client_id == payload.client_id
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        thread = Thread(
            owner_id=auth.user.id,
            client_id=payload.client_id,
            title=payload.title,
            mode=payload.mode,
        )
        db.add(thread)
    else:
        thread.title = payload.title
        thread.mode = payload.mode
    await db.commit()
    await db.refresh(thread)
    return await _thread_out(db, thread)


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: AsyncSession = Depends(get_session),
) -> ThreadDetail:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    messages = (
        (
            await db.execute(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    base = await _thread_out(db, thread)
    return ThreadDetail(**base.model_dump(), messages=[_message_out(m) for m in messages])


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def update_thread(
    thread_id: str,
    payload: ThreadUpdate,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> ThreadOut:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        thread.title = changes["title"]
    if "mode" in changes and changes["mode"] is not None:
        thread.mode = changes["mode"]
    await db.commit()
    await db.refresh(thread)
    return await _thread_out(db, thread)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: str,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    await db.delete(thread)
    await db.commit()


@router.post(
    "/threads/{thread_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_message(
    thread_id: str,
    payload: MessageCreate,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> MessageOut:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    thread.updated_at = datetime.now(UTC)
    message = (
        await db.execute(
            select(Message).where(
                Message.thread_id == thread.id, Message.client_id == payload.client_id
            )
        )
    ).scalar_one_or_none()
    if message is None:
        message = Message(
            thread_id=thread.id,
            client_id=payload.client_id,
            role=payload.role,
            text=payload.text,
            status=payload.status,
            citations=payload.citations,
            attachment_ids=payload.attachment_ids,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
    else:
        message.text = payload.text
        message.status = payload.status
        message.citations = payload.citations
        message.attachment_ids = payload.attachment_ids
        await db.commit()
        await db.refresh(message)
    return _message_out(message)


@router.delete(
    "/threads/{thread_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_message(
    thread_id: str,
    message_id: str,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> None:
    thread = await _owned_thread(db, auth.user.id, thread_id)
    thread.updated_at = datetime.now(UTC)
    message = (
        await db.execute(
            select(Message).where(
                Message.thread_id == thread.id, Message.client_id == message_id
            )
        )
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    await db.delete(message)
    await db.commit()