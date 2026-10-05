"""Evidence returned by retrieval."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from core.schemas.memory import MemoryModel, utc_now


class EvidenceLocation(MemoryModel):
    filename: str
    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class EvidenceItem(MemoryModel):
    source: Literal["document", "memory"] = "document"
    document_id: str | None = None
    chunk_id: str | None = None
    memory_id: str | None = None
    location: EvidenceLocation | None = None
    retrieval_score: float
    retrieved_at: str = Field(default_factory=utc_now)
    text: str
