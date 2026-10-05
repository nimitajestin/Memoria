"""Plain-text units."""

from __future__ import annotations

from ingestion.parsers import TextUnit


def parse_text(text: str) -> list[TextUnit]:
    normalized = text.replace("\r\n", "\n")
    stripped = normalized.strip()
    if not stripped:
        return []
    lines = normalized.split("\n")
    return [
        TextUnit(
            text=stripped,
            section=None,
            line_start=1,
            line_end=max(1, len(lines)),
        )
    ]
