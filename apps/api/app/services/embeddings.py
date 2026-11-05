"""Cliente de embeddings para una API compatible con OpenAI (`POST {base}/embeddings`).

Sirve igual un llama.cpp local con `--embeddings` que un proveedor remoto. Los vectores se
devuelven normalizados (norma 1): así el producto punto es el coseno.
"""

import math

import httpx

from ..config import settings

_BATCH = 16


class EmbeddingsError(Exception):
    """El servicio de embeddings no está disponible o respondió algo inesperado."""


def embeddings_enabled() -> bool:
    return bool(settings.embeddings_base_url and settings.embeddings_model)


def current_model() -> str | None:
    return settings.embeddings_model if embeddings_enabled() else None


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Un vector normalizado por texto, en el mismo orden."""
    if not embeddings_enabled():
        raise EmbeddingsError("Embeddings are not configured")
    base = (settings.embeddings_base_url or "").rstrip("/")
    headers = {"Authorization": f"Bearer {settings.embeddings_api_key}"} if settings.embeddings_api_key else {}
    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=settings.embeddings_timeout_seconds) as client:
        for start in range(0, len(texts), _BATCH):
            batch = texts[start : start + _BATCH]
            try:
                response = await client.post(
                    f"{base}/embeddings",
                    headers=headers,
                    json={"model": settings.embeddings_model, "input": batch},
                )
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                batch_vectors = [list(map(float, item["embedding"])) for item in data]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise EmbeddingsError(f"Embeddings request failed: {exc}") from exc
            if len(batch_vectors) != len(batch):
                raise EmbeddingsError("Embeddings response does not match the request")
            vectors.extend(_normalize(vector) for vector in batch_vectors)
    return vectors


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return vector if norm == 0 else [value / norm for value in vector]


__all__ = ["EmbeddingsError", "current_model", "embed_texts", "embeddings_enabled"]
