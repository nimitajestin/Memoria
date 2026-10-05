"""Parse imported chat transcripts into normalized turns."""

from __future__ import annotations

import json
from pathlib import Path

from core.errors import StorageError
from core.schemas.conversations import Turn


def parse_transcript(path: Path, text: str | None = None) -> tuple[str, list[Turn]]:
    suffix = path.suffix.lower()
    body = text if text is not None else path.read_text(encoding="utf-8")
    if suffix == ".json":
        return "json", parse_json_transcript(body)
    if suffix in {".md", ".markdown"}:
        return "markdown", parse_labeled_transcript(body)
    if suffix == ".txt":
        return "txt", parse_labeled_transcript(body)
    raise StorageError("UNSUPPORTED", "Import format is outside the allowlist.")


def parse_json_transcript(body: str) -> list[Turn]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise StorageError("VALIDATION", "Conversation JSON is not valid.") from exc
    if isinstance(payload, dict) and "turns" in payload:
        payload = payload["turns"]
    if not isinstance(payload, list) or not payload:
        raise StorageError("VALIDATION", "Conversation JSON must be a non-empty turn list.")
    turns: list[Turn] = []
    for item in payload:
        if not isinstance(item, dict):
            raise StorageError("VALIDATION", "Each turn must be an object.")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant", "system"} or not isinstance(content, str) or not content.strip():
            raise StorageError("VALIDATION", "Turn role or content is not valid.")
        turns.append(Turn(role=role, content=content.strip(), timestamp=item.get("timestamp")))
    return turns


def parse_labeled_transcript(text: str) -> list[Turn]:
    turns: list[Turn] = []
    role: str | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal role, lines
        if role is None:
            return
        content = "\n".join(lines).strip()
        if content:
            turns.append(Turn(role=role, content=content, timestamp=None))
        role = None
        lines = []

    for line in text.splitlines():
        if line.startswith("User:"):
            flush()
            role = "user"
            lines = [line[len("User:") :].strip()]
        elif line.startswith("Assistant:"):
            flush()
            role = "assistant"
            lines = [line[len("Assistant:") :].strip()]
        elif line.startswith("System:"):
            flush()
            role = "system"
            lines = [line[len("System:") :].strip()]
        elif role is not None:
            lines.append(line)
    flush()
    if not turns:
        raise StorageError("VALIDATION", "Transcript contained no labeled turns.")
    return turns
