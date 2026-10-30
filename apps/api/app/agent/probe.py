"""Prueba de aptitud para agentes: una llamada real con una herramienta trivial (roadmap §3.4).

Lo usa el admin ("Probar como agente") para fijar `provider_models.supports_tools`. No pasa por el
agente ni por el stream: basta con ver si el modelo devuelve una llamada válida a la herramienta.
Los fallos se clasifican sin copiar el texto del proveedor, por si repitiera algún secreto.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx
import openai
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from ..core.providers.registry import resolved_base_url
from ..models.provider import Provider, ProviderModel

PROBE_TOOL_NAME = "sofee_ping"
PROBE_TIMEOUT_SECONDS = 30.0

# Formato de herramienta de OpenAI: basta un argumento para que la llamada sea comprobable.
PROBE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": PROBE_TOOL_NAME,
        "description": "Devuelve el texto indicado. Úsala cuando te pidan un ping.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}
PROBE_PROMPT = 'Llama a la herramienta sofee_ping con el texto "ok". No respondas con texto.'

SUPPORTS = "supports"
NO_TOOL_CALL = "no_tool_call"
REJECTED = "rejected"
INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ProbeResult:
    """`supports` y `no_tool_call`/`rejected` fijan el flag; `inconclusive` lo deja como está."""

    verdict: str
    message: str
    latency_ms: int | None = None


async def probe_tool_calling(
    provider: Provider, provider_model: ProviderModel, api_key: str
) -> ProbeResult:
    base_url = resolved_base_url(provider.kind, provider.base_url)
    if not base_url:
        return ProbeResult(INCONCLUSIVE, "El provider no tiene base_url configurada.")

    started = time.monotonic()
    # Cliente httpx propio (no el interno de langchain-openai): una sola petición, con su tiempo límite.
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as http_client:
        chat = ChatOpenAI(
            model=provider_model.model_id,
            base_url=base_url,
            api_key=api_key,
            default_headers=provider.default_headers or None,
            http_async_client=http_client,
            # Misma forma de petición que el agente (sin temperatura ni límite de tokens): un 400 por
            # parámetros no soportados no debe confundirse con "no admite herramientas".
            # Una prueba no reintenta: un fallo transitorio se reporta tal cual.
            max_retries=0,
        )
        try:
            reply = await chat.bind_tools([PROBE_TOOL]).ainvoke([HumanMessage(content=PROBE_PROMPT)])
        except openai.BadRequestError:
            return ProbeResult(REJECTED, "El provider rechazó la petición con herramientas (HTTP 400).", _elapsed(started))
        except Exception as exc:  # noqa: BLE001 - cualquier otro fallo es inconcluyente, no un "no"
            return ProbeResult(INCONCLUSIVE, _inconclusive_message(exc), _elapsed(started))

    latency = _elapsed(started)
    for call in getattr(reply, "tool_calls", None) or []:
        if call.get("name") == PROBE_TOOL_NAME and isinstance(call.get("args"), dict):
            return ProbeResult(SUPPORTS, "Devolvió una llamada válida a la herramienta.", latency)
    return ProbeResult(NO_TOOL_CALL, "Respondió sin llamar a la herramienta.", latency)


def _inconclusive_message(exc: Exception) -> str:
    if isinstance(exc, openai.APIStatusError):
        return f"El provider respondió con HTTP {exc.status_code}; la prueba no es concluyente."
    return f"No hubo respuesta utilizable del provider ({type(exc).__name__}); la prueba no es concluyente."


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


__all__ = [
    "INCONCLUSIVE",
    "NO_TOOL_CALL",
    "PROBE_TOOL",
    "PROBE_TOOL_NAME",
    "REJECTED",
    "SUPPORTS",
    "ProbeResult",
    "probe_tool_calling",
]
