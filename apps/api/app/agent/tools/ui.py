"""Herramientas de presentación: emiten UI estructurada por el stream custom.

No buscan nada. El modelo llama a la herramienta, el evento `ui.*` llega al
frontend (chips de Explore, quiz de Learn) y al modelo solo le vuelve un "mostrado".
"""

from langchain_core.tools import tool
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field


class DirectionItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    why: str = Field(min_length=1, max_length=500)


class QuizItem(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=1000)


def _emit(payload: dict) -> None:
    """Escribe en el stream del run. Fuera de un grafo (tests, uso directo) no hace nada."""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(payload)


@tool
def suggest_directions(items: list[DirectionItem]) -> str:
    """Muestra al usuario de 3 a 5 direcciones para seguir explorando. Cada una tiene un título
    que puede ser la siguiente pregunta y un `why` que explica qué aportaría."""
    _emit({"type": "ui.directions", "items": [item.model_dump() for item in items]})
    return "Direcciones mostradas al usuario."


@tool
def check_understanding(items: list[QuizItem]) -> str:
    """Muestra al usuario un mini quiz de 2 a 3 preguntas con su respuesta, para que pruebe
    si ha entendido la explicación."""
    _emit({"type": "ui.quiz", "items": [item.model_dump() for item in items]})
    return "Quiz mostrado al usuario."


__all__ = ["check_understanding", "suggest_directions"]
