"""JSON lines for operational events. Record and document bodies are omitted."""

from __future__ import annotations

import json
from pathlib import Path

from core.schemas.memory import utc_now

ALLOWED_FIELDS = {
    "request_id",
    "execution_id",
    "project_id",
    "record_id",
    "document_id",
    "record_type",
    "outcome",
    "error_code",
    "count",
    "latency_ms",
    "tool",
}


def log_event(data_root: Path, event: str, **fields: object) -> None:
    payload = {
        "ts": utc_now(),
        "event": event,
    }
    for key, value in fields.items():
        if key in ALLOWED_FIELDS:
            payload[key] = value
    path = data_root / "logs" / "memoria.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        return
