import httpx
import pytest
import respx

from app.core.providers import (
    ChatMessage,
    ChatRequest,
    OpenAICompatibleAdapter,
    ProviderError,
    build_adapter,
    resolved_base_url,
)
from app.models.provider import ProviderKind

API_URL = "https://api.test/v1"


@respx.mock
async def test_list_models_parses_data():
    respx.get(f"{API_URL}/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]}
        )
    )
    adapter = OpenAICompatibleAdapter(base_url=API_URL, api_key="sk-test")
    models = await adapter.list_models()
    assert [m.id for m in models] == ["model-a", "model-b"]


@respx.mock
async def test_list_models_sends_bearer_auth():
    route = respx.get(f"{API_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m"}]})
    )
    adapter = OpenAICompatibleAdapter(base_url=API_URL, api_key="sk-secret-123")
    await adapter.list_models()
    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-secret-123"


@respx.mock
async def test_list_models_error_status():
    respx.get(f"{API_URL}/models").mock(return_value=httpx.Response(500))
    adapter = OpenAICompatibleAdapter(base_url=API_URL)
    with pytest.raises(ProviderError):
        await adapter.list_models()


@respx.mock
async def test_test_connection_ok():
    respx.get(f"{API_URL}/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})
    )
    adapter = OpenAICompatibleAdapter(base_url=API_URL)
    result = await adapter.test_connection()
    assert result.ok is True
    assert result.model_count == 2


@respx.mock
async def test_test_connection_failure():
    respx.get(f"{API_URL}/models").mock(return_value=httpx.Response(502))
    adapter = OpenAICompatibleAdapter(base_url=API_URL)
    result = await adapter.test_connection()
    assert result.ok is False
    assert result.model_count == 0


@respx.mock
async def test_chat_completion():
    respx.post(f"{API_URL}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chat-1",
                "model": "model-a",
                "choices": [{"message": {"content": "Hola"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 2},
            },
        )
    )
    adapter = OpenAICompatibleAdapter(base_url=API_URL, api_key="sk-test")
    response = await adapter.chat_completion(
        ChatRequest(model="model-a", messages=[ChatMessage(role="user", content="hola")])
    )
    assert response.content == "Hola"
    assert response.model == "model-a"


@respx.mock
async def test_chat_completion_stream():
    respx.post(f"{API_URL}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            text="data: {\"choices\":[{\"delta\":{\"content\":\"Ho\"}}]}\n\n"
            "data: {\"choices\":[{\"delta\":{\"content\":\"la\"}}]}\n\n"
            "data: [DONE]\n\n",
        )
    )
    adapter = OpenAICompatibleAdapter(base_url=API_URL)
    chunks = [c async for c in adapter.chat_completion_stream(
        ChatRequest(model="m", messages=[ChatMessage(role="user", content="hola")])
    )]
    assert [c.delta for c in chunks] == ["Ho", "la"]


def test_resolved_base_url():
    assert resolved_base_url(ProviderKind.deepinfra, None).startswith("https://api.deepinfra.com")
    assert resolved_base_url(ProviderKind.openai_compatible, None) is None
    assert resolved_base_url(ProviderKind.openai_compatible, "https://custom") == "https://custom"


def test_build_adapter_openai_compatible_requires_base_url():
    with pytest.raises(ProviderError):
        build_adapter(ProviderKind.openai_compatible, base_url=None, api_key=None)