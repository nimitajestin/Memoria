"""PDF page units. OCR is out of scope."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.errors import StorageError
from ingestion.parsers import TextUnit


def parse_pdf(data: bytes) -> list[TextUnit]:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, Exception) as exc:
        raise StorageError("VALIDATION", "PDF could not be parsed.") from exc
    units: list[TextUnit] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception as exc:
            raise StorageError("VALIDATION", "PDF page text could not be extracted.") from exc
        body = extracted.strip()
        if body:
            units.append(TextUnit(text=body, section=None, page=number, line_start=None, line_end=None))
    if not units:
        raise StorageError("VALIDATION", "PDF has no extractable text layer.")
    del reader
    return units
