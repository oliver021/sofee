"""Recupera las llamadas a herramientas de UI que un modelo pequeño escribe como texto.

A veces un modelo local no emite la llamada a `suggest_directions` o `check_understanding` en el
formato que entiende el servidor del modelo, y la deja al final de la respuesta como
`suggest_directions {"items": [...]}`. Si el JSON valida contra el esquema de la herramienta, se
quita del texto y se devuelve como el evento `ui.*` que la herramienta habría emitido: el usuario
ve los chips o el quiz de siempre y no un bloque de JSON. Cualquier otra cosa se deja como está.
"""

import json
import re

from pydantic import BaseModel, TypeAdapter, ValidationError

from .tools.ui import DirectionItem, QuizItem

_CALLS: dict[str, tuple[str, type[BaseModel]]] = {
    "suggest_directions": ("ui.directions", DirectionItem),
    "check_understanding": ("ui.quiz", QuizItem),
}
_CALL_START = re.compile(
    r"^[ \t]*(?:`{1,3}[a-z]*\s*)?(" + "|".join(_CALLS) + r")[ \t]*[:(]?\s*(?=\{)", re.MULTILINE
)
_decoder = json.JSONDecoder()


def recover_leaked_ui_calls(text: str) -> tuple[str, list[tuple[str, dict]]]:
    """(texto sin las llamadas recuperadas, [(tipo de evento, payload)])."""
    events: list[tuple[str, dict]] = []
    kept: list[str] = []
    position = 0
    for match in _CALL_START.finditer(text):
        if match.start() < position:
            continue
        try:
            body, end = _decoder.raw_decode(text, match.end())
        except ValueError:
            continue
        items = body.get("items") if isinstance(body, dict) else None
        event_type, model = _CALLS[match.group(1)]
        try:
            valid = TypeAdapter(list[model]).validate_python(items)
        except ValidationError:
            continue
        if not valid:
            continue
        # La llamada puede venir cerrada con `)` o con una cerca de código.
        tail = re.match(r"\s*\)?\s*(?:`{3})?", text[end:])
        end += tail.end() if tail else 0
        kept.append(text[position : match.start()])
        position = end
        events.append((event_type, {"items": [item.model_dump() for item in valid]}))
    if not events:
        return text, []
    kept.append(text[position:])
    return re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip(), events


__all__ = ["recover_leaked_ui_calls"]
