"""Document and chunk models stored in the vault index."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from core.safety import PROJECT_ID_RE
from core.schemas.memory import MemoryModel, _timestamp

FILE_TYPES = {
    "pdf",
    "markdown",
    "text",
    "docx",
    "python",
    "javascript",
    "typescript",
    "c",
    "cpp",
    "java",
    "source",
}

DocumentStatus = Literal["pending", "indexed", "empty", "failed", "truncated", "unsupported"]


class DocumentMeta(MemoryModel):
    id: str
    project_id: str
    filename: str = Field(min_length=1, max_length=128)
    file_type: str
    byte_size: int = Field(ge=0)
    content_hash: str
    indexed_at: str | None = None
    status: DocumentStatus
    error: str | None = Field(default=None, max_length=500)
    chunk_count: int = Field(default=0, ge=0)
    vault_relpath: str

    @model_validator(mode="after")
    def check(self) -> DocumentMeta:
        if PROJECT_ID_RE.fullmatch(self.project_id) is None:
            raise ValueError("invalid project id")
        if re.fullmatch(r"^doc_[0-9a-f]{12}$", self.id) is None:
            raise ValueError("invalid document id")
        if self.file_type not in FILE_TYPES:
            raise ValueError("unsupported file type")
        if len(self.content_hash) != 64:
            raise ValueError("content hash must be sha256 hex")
        if self.indexed_at is not None:
            self.indexed_at = _timestamp(self.indexed_at)
        if ".." in self.vault_relpath or self.vault_relpath.startswith(("/", "\\")):
            raise ValueError("vault path escapes the data root")
        return self


class ChunkRecord(MemoryModel):
    id: str
    document_id: str
    project_id: str
    chunk_index: int = Field(ge=0)
    section: str | None = None
    page: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    content_hash: str
    char_count: int = Field(ge=0)
    text: str
    created_at: str

    @model_validator(mode="after")
    def check(self) -> ChunkRecord:
        if re.fullmatch(r"^chunk_[0-9a-f]{12}$", self.id) is None:
            raise ValueError("invalid chunk id")
        if len(self.content_hash) != 64:
            raise ValueError("content hash must be sha256 hex")
        if self.char_count != len(self.text):
            raise ValueError("char_count does not match text")
        self.created_at = _timestamp(self.created_at)
        return self


class EmbeddingRecord(MemoryModel):
    chunk_id: str
    model: str = Field(min_length=1, max_length=128)
    dimension: int = Field(ge=1, le=4096)
    vector: bytes
    created_at: str

    @model_validator(mode="after")
    def check(self) -> EmbeddingRecord:
        if len(self.vector) != self.dimension * 4:
            raise ValueError("vector byte length does not match dimension")
        self.created_at = _timestamp(self.created_at)
        return self
