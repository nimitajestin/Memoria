"""Split parsed units into bounded chunks."""

from __future__ import annotations

from dataclasses import dataclass

from ingestion.parsers import TextUnit

TARGET = 800
MAXIMUM = 1200
OVERLAP = 100
CAP = 500


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    section: str | None
    page: int | None
    line_start: int | None
    line_end: int | None


def chunk_units(units: list[TextUnit], *, target: int = TARGET, maximum: int = MAXIMUM, overlap: int = OVERLAP) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for unit in units:
        drafts.extend(_split_unit(unit, target=target, maximum=maximum, overlap=overlap))
    return drafts


def _split_unit(unit: TextUnit, *, target: int, maximum: int, overlap: int) -> list[ChunkDraft]:
    text = unit.text.strip()
    if not text:
        return []
    if len(text) <= maximum:
        return [
            ChunkDraft(
                text=text,
                section=unit.section,
                page=unit.page,
                line_start=unit.line_start,
                line_end=unit.line_end,
            )
        ]
    pieces: list[ChunkDraft] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target)
        if end < len(text):
            window = text[start : min(len(text), start + maximum)]
            split = _break_at(window, target)
            end = start + split
        piece = text[start:end].strip()
        if piece:
            line_start = _line_at(text, start, unit.line_start)
            line_end = _line_at(text, end - 1, unit.line_start)
            pieces.append(
                ChunkDraft(
                    text=piece,
                    section=unit.section,
                    page=unit.page,
                    line_start=line_start,
                    line_end=line_end,
                )
            )
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def _break_at(window: str, target: int) -> int:
    if len(window) <= target:
        return len(window)
    cut = window.rfind("\n", 0, target)
    if cut >= target // 2:
        return cut + 1
    cut = window.rfind(" ", 0, target)
    if cut >= target // 2:
        return cut + 1
    return min(len(window), target)


def _line_at(text: str, index: int, origin: int | None) -> int | None:
    if origin is None:
        return None
    return origin + text[: max(0, index)].count("\n")
