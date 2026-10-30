from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .conversation import ComposerMode

RunKind = Literal["send", "regenerate", "continue"]
ResumeDecision = Literal["approve", "edit", "reject"]
TodoStatus = Literal["pending", "in_progress", "completed"]

__all__ = [
    "ClearOut",
    "CompactOut",
    "FeedbackIn",
    "FileContentOut",
    "FileOut",
    "RunCreate",
    "RunCreated",
    "RunEventOut",
    "RunOut",
    "RunResume",
    "RunSummaryOut",
    "RunTodo",
    "RunUserMessage",
    "StarterOut",
]


class RunUserMessage(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)
    attachment_ids: list[str] | None = None


class RunCreate(BaseModel):
    kind: RunKind
    assistant_client_id: str = Field(min_length=1, max_length=200)
    mode: ComposerMode
    model_slug: str | None = Field(default=None, max_length=200)
    # Obligatorio en `send`; en `regenerate` y `continue` se ignora.
    user_message: RunUserMessage | None = None


class RunCreated(BaseModel):
    run_id: str
    assistant_message_id: str
    status: str


class RunTodo(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    status: TodoStatus


class RunResume(BaseModel):
    decision: ResumeDecision
    todos: list[RunTodo] | None = None


class RunEventOut(BaseModel):
    seq: int
    type: str
    payload: dict[str, Any]


class RunSummaryOut(BaseModel):
    run_id: str
    assistant_message_id: str
    status: str
    mode: str
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(RunSummaryOut):
    events: list[RunEventOut]


class FeedbackIn(BaseModel):
    value: Literal["good", "bad"] | None = None
    reason: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)


class CompactOut(BaseModel):
    summary_through_seq: int | None


class ClearOut(BaseModel):
    context_start_seq: int


class StarterOut(BaseModel):
    text: str


class FileOut(BaseModel):
    path: str
    size: int
    updated_at: str


class FileContentOut(BaseModel):
    path: str
    content: str
