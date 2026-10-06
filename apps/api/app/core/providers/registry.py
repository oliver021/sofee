from ...models.provider import ProviderKind
from .base import ProviderAdapter, ProviderError
from .openai import OpenAICompatibleAdapter

DEFAULT_BASE_URLS: dict[ProviderKind, str | None] = {
    ProviderKind.vercel_gateway: "https://ai-gateway.vercel.sh/v1",
    ProviderKind.deepinfra: "https://api.deepinfra.com/v1/openai",
    ProviderKind.nvidia_nim: "https://integrate.api.nvidia.com/v1",
    ProviderKind.openai_compatible: None,
}

REGISTRY: dict[ProviderKind, type[OpenAICompatibleAdapter]] = {
    ProviderKind.vercel_gateway: OpenAICompatibleAdapter,
    ProviderKind.deepinfra: OpenAICompatibleAdapter,
    ProviderKind.nvidia_nim: OpenAICompatibleAdapter,
    ProviderKind.openai_compatible: OpenAICompatibleAdapter,
}


def resolved_base_url(kind: ProviderKind, configured: str | None) -> str | None:
    if configured:
        return configured
    return DEFAULT_BASE_URLS.get(kind)


def build_adapter(
    kind: ProviderKind,
    base_url: str | None,
    api_key: str | None,
    default_headers: dict | None = None,
) -> ProviderAdapter:
    adapter_cls = REGISTRY[kind]
    resolved = resolved_base_url(kind, base_url)
    if kind is ProviderKind.openai_compatible and not resolved:
        raise ProviderError("base_url is required for openai_compatible providers")
    return adapter_cls(
        base_url=resolved or "",
        api_key=api_key,
        default_headers=default_headers or {},
    )