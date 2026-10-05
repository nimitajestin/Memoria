"""Markdown heading-aware units."""

from __future__ import annotations

import re

from ingestion.parsers import TextUnit

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_markdown(text: str) -> list[TextUnit]:
    lines = text.replace("\r\n", "\n").split("\n")
    units: list[TextUnit] = []
    section: str | None = None
    start = 1
    buf: list[str] = []

    def flush(end: int) -> None:
        body = "\n".join(buf).strip()
        if body:
            units.append(TextUnit(text=body, section=section, line_start=start, line_end=end))

    for index, line in enumerate(lines, start=1):
        match = HEADING.match(line)
        if match:
            if buf:
                flush(index - 1)
                buf = []
            section = match.group(2).strip() or None
            start = index
            buf = [line]
        else:
            if not buf:
                start = index
            buf.append(line)
    if buf:
        flush(len(lines))
    return units
