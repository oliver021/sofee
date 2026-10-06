from collections.abc import AsyncIterator, Mapping

import httpx

from .base import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ConnectionCheckResult,
    ModelInfo,
    ProviderError,
)

_AUTH_PREFIX = "Authorization"
_BEARER_PREFIX = "Bearer "


class OpenAICompatibleAdapter:
    """Adaptador para cualquier endpoint compatible con OpenAI chat completions.

    Cubre los cuatro `kind` del plan: Vercel AI Gateway, DeepInfra y NVIDIA NIM
    se comportan como este mismo adaptador con base_url provisto por el registro;
    `openai_compatible` aporta su propia base_url.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not base_url:
            raise ProviderError("base_url is required for this provider")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_headers = dict(default_headers or {})
        self.timeout = timeout

    def _auth_headers(self) -> dict[str, str]:
        headers = dict(self.default_headers)
        if self.api_key:
            headers[_AUTH_PREFIX] = f"{_BEARER_PREFIX}{self.api_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout)

    async def list_models(self) -> list[ModelInfo]:
        url = f"{self.base_url}/models"
        try:
            async with self._client() as client:
                resp = await client.get(url, headers=self._auth_headers())
            if resp.status_code != 200:
                raise ProviderError(f"List models failed with HTTP {resp.status_code}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {type(exc).__name__}")
        models = [
            ModelInfo(id=item.get("id", ""), display_name=item.get("id"))
            for item in data.get("data", [])
            if item.get("id")
        ]
        if not models:
            raise ProviderError("Empty model list returned by provider")
        return models

    async def test_connection(self) -> ConnectionCheckResult:
        try:
            models = await self.list_models()
            return ConnectionCheckResult(
                ok=True,
                message=f"Connected, {len(models)} models available",
                model_count=len(models),
            )
        except ProviderError as exc:
            return ConnectionCheckResult(ok=False, message=str(exc), model_count=0)

    def _chat_payload(self, request: ChatRequest) -> dict:
        payload: dict = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return payload

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        url = f"{self.base_url}/chat/completions"
        try:
            async with self._client() as client:
                resp = await client.post(
                    url, json=self._chat_payload(request), headers=self._auth_headers()
                )
            if resp.status_code != 200:
                raise ProviderError(f"Chat completion failed with HTTP {resp.status_code}")
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {type(exc).__name__}")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return ChatResponse(
            id=data.get("id"),
            model=data.get("model") or request.model,
            content=message.get("content") or "",
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
        )

    async def chat_completion_stream(
        self, request: ChatRequest
    ) -> AsyncIterator[ChatChunk]:
        url = f"{self.base_url}/chat/completions"
        payload = self._chat_payload(request)
        payload["stream"] = True
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST", url, json=payload, headers=self._auth_headers()
                ) as resp:
                    if resp.status_code != 200:
                        raise ProviderError(
                            f"Chat completion stream failed with HTTP {resp.status_code}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk = line[len("data: ") :]
                        if chunk == "[DONE]":
                            break
                        delta = _parse_delta(chunk)
                        if delta is not None:
                            yield delta
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {type(exc).__name__}")


def _parse_delta(payload: str) -> ChatChunk | None:
    import json

    try:
        data = json.loads(payload)
    except ValueError:
        return None
    choice = (data.get("choices") or [{}])[0]
    delta = choice.get("delta") or {}
    return ChatChunk(delta=delta.get("content") or "", finish_reason=choice.get("finish_reason"))