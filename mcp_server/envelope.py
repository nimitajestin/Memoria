"""JSON envelopes for MCP tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from core.errors import StorageError


def ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, default=str)


def err(code: str, message: str, details: dict | None = None) -> str:
    return json.dumps(
        {"ok": False, "error": {"code": code, "message": message, "details": details or {}}},
        default=str,
    )


def run_tool(action: Callable[[], Any]) -> str:
    try:
        return ok(action())
    except StorageError as exc:
        return err(exc.code, str(exc), exc.details)
    except Exception:
        return err("INTERNAL", "Unexpected server error.")
