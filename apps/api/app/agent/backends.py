"""Sistema de archivos virtual del agente: un `CompositeBackend` por prefijo.

- `/kb/`, `/attachments/`: `StoreBackend` de solo lectura (ver `READ_ONLY_PERMISSIONS`).
- `/notes/`: `StoreBackend` por hilo, lectura y escritura.
- resto: `StateBackend` (vida del run).

Los namespaces salen de `runtime.context`, así que el mismo backend sirve al agente
principal y a todos los subagentes sin reconstruirse.
"""

from collections.abc import Callable

from deepagents import FilesystemPermission
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.runtime import Runtime

from .context import SofeeContext

KB_NAMESPACE = ("kb",)


def _kb_namespace(_runtime: Runtime[SofeeContext]) -> tuple[str, ...]:
    return KB_NAMESPACE


def _thread_namespace(suffix: str) -> Callable[[Runtime[SofeeContext]], tuple[str, ...]]:
    def namespace(runtime: Runtime[SofeeContext]) -> tuple[str, ...]:
        return (runtime.context.thread_id, suffix)

    return namespace


# `deny` sobre escritura: write_file, edit_file y delete fallan con un error legible
# para el modelo. Se aplica a todos los agentes creados con `create_deep_agent`
# (los subagentes heredan `permissions` salvo que declaren la suya).
READ_ONLY_PERMISSIONS = [
    FilesystemPermission(
        operations=["write"],
        paths=["/kb/**", "/attachments/**"],
        mode="deny",
    ),
]


def make_backend() -> CompositeBackend:
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/kb/": StoreBackend(namespace=_kb_namespace),
            "/attachments/": StoreBackend(namespace=_thread_namespace("attachments")),
            "/notes/": StoreBackend(namespace=_thread_namespace("notes")),
        },
    )


__all__ = ["KB_NAMESPACE", "READ_ONLY_PERMISSIONS", "make_backend"]
