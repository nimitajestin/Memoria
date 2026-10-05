"""Parsed document units before chunking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextUnit:
    text: str
    section: str | None = None
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
