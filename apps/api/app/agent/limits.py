"""Límites por run que se aplican en el middleware: número de subagentes (roadmap §3.11).

El de búsquedas vive en las herramientas (`tools/search.py`), porque cada búsqueda ya pasa por
ellas. Los contadores están en el registro del run, así que los comparten el agente principal
y los subagentes, y se reconstruyen al reanudar (ver `executor._ensure_loaded`).
"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from .sources import get_registry

TASK_TOOL = "task"


class SubagentLimitMiddleware(AgentMiddleware):
    """Rechaza las llamadas a `task` por encima de `max_subagents` en el run."""

    def __init__(self, max_subagents: int) -> None:
        super().__init__()
        self.max_subagents = max_subagents

    def wrap_tool_call(self, request: ToolCallRequest, handler):  # noqa: ANN001, ANN201
        blocked = self._claim(request)
        return blocked if blocked is not None else handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):  # noqa: ANN001, ANN201
        blocked = self._claim(request)
        return blocked if blocked is not None else await handler(request)

    def _claim(self, request: ToolCallRequest) -> ToolMessage | None:
        if request.tool_call["name"] != TASK_TOOL:
            return None
        registry = get_registry(request.runtime.context.run_id)
        already = registry.subagents
        registry.subagents += 1
        if already >= self.max_subagents:
            return _refusal(request.tool_call, self.max_subagents)
        return None


def _refusal(tool_call: dict[str, Any], limit: int) -> ToolMessage:
    return ToolMessage(
        content=(
            f"Error: se alcanzó el límite de {limit} subagentes para este run. "
            "Responde con lo que ya tienes y di lo que no pudiste verificar."
        ),
        tool_call_id=str(tool_call.get("id") or ""),
        name=TASK_TOOL,
        status="error",
    )


__all__ = ["SubagentLimitMiddleware", "TASK_TOOL"]
