from dataclasses import dataclass


@dataclass(frozen=True)
class SofeeContext:
    """Contexto inmutable de un run, pasado a `astream(context=...)`.

    Las rutas de `/notes/`, `/attachments/` y de los subagentes se resuelven
    con `runtime.context` (ver `backends.py`), así que todo lo que dependa del
    usuario o del hilo viaja aquí y no en el estado del agente.
    """

    user_id: str
    thread_id: str  # id interno (UUID) del hilo, como texto
    run_id: str
    mode: str
    locale: str
