"""Top-level function and class units. Files are read as text, never executed."""

from __future__ import annotations

import re

from ingestion.parsers import TextUnit
from ingestion.parsers.text import parse_text

PATTERNS = {
    "python": re.compile(r"^(async\s+def|def|class)\s+\S+", re.MULTILINE),
    "javascript": re.compile(
        r"^((export\s+)?(async\s+)?function\s+\S+|class\s+\S+|(export\s+)?const\s+\S+\s*=\s*(async\s*)?\()",
        re.MULTILINE,
    ),
    "typescript": re.compile(
        r"^((export\s+)?(async\s+)?function\s+\S+|class\s+\S+|(export\s+)?(type|interface)\s+\S+)",
        re.MULTILINE,
    ),
    "c": re.compile(r"^[\w\s\*]+\s+\w+\s*\([^;]*\)\s*\{", re.MULTILINE),
    "cpp": re.compile(r"^(class\s+\S+|[\w\s\*:]+?\s+\w+\s*\([^;]*\)\s*\{)", re.MULTILINE),
    "java": re.compile(
        r"^(\s*)(public|private|protected|static|\s)*(class|interface|enum|void|\w+)\s+\w+[^{;]*\{",
        re.MULTILINE,
    ),
}


def parse_code(text: str, file_type: str) -> list[TextUnit]:
    normalized = text.replace("\r\n", "\n")
    pattern = PATTERNS.get(file_type)
    if pattern is None:
        return parse_text(normalized)
    starts = [match.start() for match in pattern.finditer(normalized)]
    if not starts:
        return parse_text(normalized)
    starts.append(len(normalized))
    units: list[TextUnit] = []
    prefix = normalized[: starts[0]].strip()
    if prefix:
        line_end = prefix.count("\n") + 1
        units.append(TextUnit(text=prefix, section="module", line_start=1, line_end=line_end))
    for begin, end in zip(starts, starts[1:]):
        body = normalized[begin:end].strip()
        if not body:
            continue
        line_start = normalized[:begin].count("\n") + 1
        line_end = line_start + body.count("\n")
        first = body.split("\n", 1)[0].strip()
        units.append(TextUnit(text=body, section=first[:120], line_start=line_start, line_end=line_end))
    return units
