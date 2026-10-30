"""Modelo de chat falso para los tests del agente: un guion de AIMessages, sin red.

`bind_tools` devuelve el mismo modelo, así que las llamadas a herramientas son las del
guion. El streaming emite tokens de texto y las llamadas como `tool_call_chunks`, igual
que un proveedor real.
"""

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

MODEL_NAME = "scripted-test"


def ai(
    content: str = "",
    calls: list[tuple[str, dict[str, Any], str]] | tuple = (),
    *,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> AIMessage:
    """Una respuesta del guion: texto y/o llamadas `(nombre, args, id)`."""
    return AIMessage(
        content=content,
        id=f"msg-{uuid.uuid4()}",
        tool_calls=[{"name": name, "args": args, "id": call_id} for name, args, call_id in calls],
        response_metadata={"model_name": MODEL_NAME},
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class ScriptedChatModel(BaseChatModel):
    """Devuelve el guion en orden. Si se agota, falla: un test no debe pedir más respuestas."""

    script: list[AIMessage]
    calls_made: int = 0
    # Mensajes de entrada de cada llamada, para comprobar qué historial recibió el modelo.
    seen: list[list[Any]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-test"

    @property
    def model_name(self) -> str:
        return MODEL_NAME

    def _get_ls_params(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ARG002
        return {"ls_provider": "openai", "ls_model_name": MODEL_NAME, "ls_model_type": "chat"}

    def bind_tools(self, tools, **kwargs: Any):  # noqa: ANN001, ANN201, ARG002
        return self

    def _next(self) -> AIMessage:
        if self.calls_made >= len(self.script):
            raise AssertionError("ScriptedChatModel: el guion no tiene más respuestas")
        message = self.script[self.calls_made]
        self.calls_made += 1
        return message

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:  # noqa: ANN001, ARG002
        self.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:  # noqa: ANN001, ARG002
        self.seen.append(list(messages))
        message = self._next()
        for token in str(message.content).split(" "):
            if token:
                yield ChatGenerationChunk(message=AIMessageChunk(content=token + " ", id=message.id))
        tool_chunks = [
            {"name": call["name"], "args": json.dumps(call["args"]), "id": call["id"], "index": index}
            for index, call in enumerate(message.tool_calls)
        ]
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                id=message.id,
                tool_call_chunks=tool_chunks,
                usage_metadata=message.usage_metadata,
                response_metadata={"model_name": MODEL_NAME},
                chunk_position="last",
            )
        )


class FailingChatModel(BaseChatModel):
    """Simula un proveedor caído: cada llamada lanza error."""

    @property
    def _llm_type(self) -> str:
        return "failing-test"

    def bind_tools(self, tools, **kwargs: Any):  # noqa: ANN001, ANN201, ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:  # noqa: ANN001, ARG002
        raise RuntimeError("provider caído (simulado)")


class GatedChatModel(ScriptedChatModel):
    """Como ScriptedChatModel, pero en streaming asíncrono se pausa tras el primer token hasta
    que `gate` se active. Permite cancelar, medir o reconectar a mitad de un run, sin tiempos."""

    gate: Any = None

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:  # noqa: ANN001, ARG002
        self.seen.append(list(messages))
        message = self._next()
        first = True
        for token in str(message.content).split(" "):
            if not token:
                continue
            yield ChatGenerationChunk(message=AIMessageChunk(content=token + " ", id=message.id))
            if first:
                first = False
                await self.gate.wait()
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                id=message.id,
                usage_metadata=message.usage_metadata,
                response_metadata={"model_name": MODEL_NAME},
                chunk_position="last",
            )
        )


class ProviderOutageChatModel(BaseChatModel):
    """Simula un 500 del proveedor con el error real de openai (sin red)."""

    @property
    def _llm_type(self) -> str:
        return "outage-test"

    def _get_ls_params(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ARG002
        return {"ls_provider": "openai", "ls_model_name": MODEL_NAME, "ls_model_type": "chat"}

    def bind_tools(self, tools, **kwargs: Any):  # noqa: ANN001, ANN201, ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:  # noqa: ANN001, ARG002
        raise _outage()

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:  # noqa: ANN001, ARG002
        raise _outage()
        yield  # pragma: no cover - hace de este método un generador asíncrono


def _outage() -> openai.InternalServerError:
    import httpx

    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    return openai.InternalServerError("upstream down (simulado)", response=httpx.Response(500, request=request), body=None)


__all__ = [
    "GatedChatModel",
    "FailingChatModel",
    "ProviderOutageChatModel",
    "ScriptedChatModel",
    "ai",
]
