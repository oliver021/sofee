import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ComposerMode = Literal["learn", "research", "explore"]
MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["pending", "streaming", "complete", "stopped", "error"]

__all__ = [
    "ComposerMode",
    "MessageCreate",
    "MessageOut",
    "MessageRole",
    "MessageStatus",
    "ThreadCreate",
    "ThreadDetail",
    "ThreadOut",
    "ThreadUpdate",
]


class ThreadCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=500)
    mode: ComposerMode = "learn"


class ThreadUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    mode: ComposerMode | None = None


class MessageCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    role: MessageRole
    text: str = Field(max_length=100_000)
    status: MessageStatus = "complete"
    citations: list[Any] | None = None
    attachment_ids: list[str] | None = None


class MessageOut(BaseModel):
    # `id` es el client_id del frontend; el frontend nunca ve el UUID interno.
    id: str
    role: MessageRole
    text: str
    status: MessageStatus
    citations: list[Any] | None
    attachment_ids: list[str] | None
    seq: int
    created_at: datetime


class ThreadOut(BaseModel):
    id: str
    title: str | None
    mode: ComposerMode
    message_count: int
    created_at: datetime
    updated_at: datetime


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]