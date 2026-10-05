"""Dispatch parse by detected file type."""

from __future__ import annotations

from pathlib import Path

from core.errors import StorageError
from ingestion.parsers import TextUnit
from ingestion.parsers.code import parse_code
from ingestion.parsers.detect import CODE_TYPES, detect_type
from ingestion.parsers.docx import parse_docx
from ingestion.parsers.markdown import parse_markdown
from ingestion.parsers.pdf import parse_pdf
from ingestion.parsers.text import parse_text


def parse_bytes(path: Path, data: bytes) -> tuple[str, list[TextUnit]]:
    kind = detect_type(path)
    if kind == "pdf":
        return kind, parse_pdf(data)
    if kind == "docx":
        return kind, parse_docx(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StorageError("VALIDATION", "Text document is not valid UTF-8.") from exc
    if kind == "markdown":
        return kind, parse_markdown(text)
    if kind == "text":
        return kind, parse_text(text)
    if kind in CODE_TYPES:
        return kind, parse_code(text, kind)
    raise StorageError("UNSUPPORTED", "File type is not in the ingestion allowlist.")
