"""DOCX paragraph and heading units."""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from core.errors import StorageError
from ingestion.parsers import TextUnit


def parse_docx(data: bytes) -> list[TextUnit]:
    try:
        document = Document(BytesIO(data))
    except (PackageNotFoundError, ValueError, Exception) as exc:
        raise StorageError("VALIDATION", "DOCX could not be parsed.") from exc
    units: list[TextUnit] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            units.append(TextUnit(text=body, section=section))

    for paragraph in document.paragraphs:
        style = (paragraph.style.name or "") if paragraph.style is not None else ""
        text = paragraph.text.strip()
        if style.startswith("Heading"):
            flush()
            buf = []
            section = text or style
            if text:
                buf = [text]
        elif text:
            buf.append(text)
    flush()
    del document
    return units
