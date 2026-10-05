from io import BytesIO

import pytest
from docx import Document
from pypdf import PdfWriter

from core.errors import StorageError
from ingestion.parsers.code import parse_code
from ingestion.parsers.docx import parse_docx
from ingestion.parsers.markdown import parse_markdown
from ingestion.parsers.pdf import parse_pdf
from ingestion.parsers.text import parse_text


def test_markdown_is_split_on_headings() -> None:
    units = parse_markdown("# One\nAlpha\n\n## Two\nBeta")
    assert [item.section for item in units] == ["One", "Two"]
    assert "Alpha" in units[0].text


def test_python_is_split_on_functions() -> None:
    source = "x = 1\n\ndef harbor_chunk_limit():\n    return 500\n\ndef other():\n    return 1\n"
    units = parse_code(source, "python")
    names = [item.section for item in units]
    assert "module" in names
    assert any(item and "harbor_chunk_limit" in item for item in names)


def test_pdf_without_text_is_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(StorageError) as caught:
        parse_pdf(buffer.getvalue())
    assert "text" in str(caught.value).lower() or caught.value.code == "VALIDATION"


def test_corrupt_pdf_is_a_parse_failure() -> None:
    with pytest.raises(StorageError):
        parse_pdf(b"not a pdf")


def test_docx_headings() -> None:
    document = Document()
    document.add_heading("Limits", level=1)
    document.add_paragraph("Harbor stores at most 500 chunks per document.")
    buffer = BytesIO()
    document.save(buffer)
    units = parse_docx(buffer.getvalue())
    assert any("500" in item.text for item in units)


def test_empty_text_has_no_units() -> None:
    assert parse_text("  \n") == []
