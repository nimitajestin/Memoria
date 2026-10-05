"""Normalized text used for duplicate and conflict checks."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any


def normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(folded.split())


def content_hash(parts: list[str]) -> str:
    joined = "\n".join(normalize_text(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(kind: str, fields: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return content hash, identity hash, and topic for one record or candidate."""

    if kind == "fact":
        digest = content_hash([fields["statement"]])
        return digest, digest, fields.get("topic")
    if kind == "decision":
        digest = content_hash([fields["decision"], fields["reason"]])
        return digest, digest, fields.get("topic")
    if kind == "goal":
        identity = content_hash([fields["statement"]])
        digest = content_hash([fields["statement"], fields.get("goal_status") or "open"])
        return digest, identity, None
    if kind == "knowledge":
        return content_hash([fields["body"]]), content_hash([fields["title"], fields["body"]]), fields.get("title")
    if kind == "episode":
        digest = content_hash([fields["summary"]])
        return digest, digest, None
    if kind == "conversation_summary":
        digest = content_hash([fields["summary"]])
        return digest, digest, None
    if kind == "status":
        blockers = fields.get("blockers") or []
        digest = content_hash([fields["phase"], fields["summary"], "\n".join(blockers)])
        return digest, digest, None
    raise ValueError(f"unknown record type: {kind}")


def searchable_text(record: Any) -> str:
    parts: list[str] = []
    for name in ("topic", "title", "statement", "decision", "reason", "summary", "body", "phase"):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            parts.append(value)
    for name in ("tags", "blockers"):
        values = getattr(record, name, None)
        if values:
            parts.extend(str(item) for item in values)
    return "\n".join(parts)


def title_or_topic(record: Any) -> str:
    for name in ("topic", "title", "phase"):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            return value
    for name in ("statement", "summary", "decision"):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            return value[:80]
    return str(record.id)
