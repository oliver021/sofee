"""Troceado de documentos para el RAG: por encabezados y párrafos, con solape.

Un trozo conserva el encabezado bajo el que está, para que un pasaje suelto siga diciendo de
qué trata. Es lógica pura: no toca la base ni la red.
"""

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MIN_CHUNK_CHARS = 40


@dataclass(frozen=True)
class Chunk:
    position: int
    heading: str
    text: str


def chunk_text(text: str, *, max_chars: int, overlap_chars: int) -> list[Chunk]:
    """Parte `text` en trozos de a lo sumo `max_chars` (más el solape), respetando párrafos."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    overlap = max(0, min(overlap_chars, max_chars // 2))
    pieces: list[tuple[str, str]] = []
    for heading, body in _sections(text):
        for part in _split_section(body, max_chars):
            pieces.append((heading, part))

    chunks: list[Chunk] = []
    previous_heading = None
    previous_text = ""
    for heading, part in pieces:
        # El solape solo se arrastra dentro de la misma sección: entre secciones no tiene sentido.
        tail = previous_text[-overlap:] if overlap and heading == previous_heading else ""
        body = f"{tail} {part}".strip() if tail else part
        last = chunks[-1] if chunks else None
        if (
            last is not None
            and len(body) < _MIN_CHUNK_CHARS
            and last.heading == heading
            and len(last.text) + 2 + len(body) <= max_chars
        ):
            # Un resto diminuto se pega al trozo anterior (si cabe) en vez de quedar como pasaje suelto.
            chunks[-1] = Chunk(last.position, last.heading, f"{last.text}\n\n{body}")
        else:
            chunks.append(Chunk(position=len(chunks), heading=heading, text=body))
        previous_heading, previous_text = heading, part
    return chunks


def _sections(text: str) -> list[tuple[str, str]]:
    """(encabezado vigente, cuerpo) por cada sección; el texto previo al primer encabezado va sin él."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            sections.append((match.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "".join(lines).strip()]


def _split_section(body: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    parts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in _hard_split(paragraph, max_chars):
            if current and len(current) + 2 + len(piece) > max_chars:
                parts.append(current)
                current = piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
    if current:
        parts.append(current)
    return parts


def _hard_split(paragraph: str, max_chars: int) -> list[str]:
    """Un párrafo más largo que el límite se corta en espacios; nunca en mitad de una palabra."""
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    rest = paragraph
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars)
        cut = cut if cut > max_chars // 2 else max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


__all__ = ["Chunk", "chunk_text"]
