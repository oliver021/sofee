from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


class ChatResponse(BaseModel):
    id: str | None = None
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict | None = None


class ChatChunk(BaseModel):
    delta: str
    finish_reason: str | None = None


class ModelInfo(BaseModel):
    id: str
    display_name: str | None = None


class ConnectionCheckResult(BaseModel):
    ok: bool
    message: str
    model_count: int = Field(default=0)


class ProviderError(Exception):
    pass


class ProviderAdapter(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...

    async def test_connection(self) -> ConnectionCheckResult: ...

    async def chat_completion(self, request: ChatRequest) -> ChatResponse: ...

    async def chat_completion_stream(
        self, request: ChatRequest
    ) -> AsyncIterator[ChatChunk]: ...