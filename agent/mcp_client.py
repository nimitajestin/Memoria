"""System C backend. Talks to MCP only; never opens the vault itself."""

from __future__ import annotations

import json
from typing import Any

import anyio
from mcp import Client

from core.errors import StorageError

TOOL_CAP = 4


class MCPUnavailable(StorageError):
    def __init__(self, message: str = "MCP is unavailable.") -> None:
        super().__init__("FAILED_DEPENDENCY", message)


class MCPBackend:
    def __init__(self, server=None, url: str | None = None) -> None:
        if server is None and not url:
            raise StorageError("VALIDATION", "MCP backend needs a server or a URL.")
        self._server = server
        self._url = url
        self.calls = 0

    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        data = self.call_tool("memory.search", {"project_id": project_id, "query": query, "limit": limit})
        return list(data.get("hits") or [])

    def search_documents(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        data = self.call_tool("documents.search", {"project_id": project_id, "query": query, "limit": limit})
        hits = []
        for item in data.get("hits") or []:
            hits.append(
                {
                    "chunk_id": item.get("chunk_id"),
                    "document_id": item.get("document_id"),
                    "text": item.get("text"),
                    "retrieval_score": item.get("retrieval_score"),
                    "location": item.get("location"),
                }
            )
        return hits

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.calls >= TOOL_CAP:
            raise StorageError("VALIDATION", "Tool call cap for this turn was reached.")
        self.calls += 1
        try:
            payload = _invoke(self._server, self._url, name, arguments)
        except StorageError:
            raise
        except Exception as exc:
            raise MCPUnavailable() from exc
        if not payload.get("ok"):
            error = payload.get("error") or {}
            raise StorageError(str(error.get("code") or "INTERNAL"), str(error.get("message") or "Tool failed."))
        data = payload.get("data")
        return data if isinstance(data, dict) else {}


def _invoke(server, url: str | None, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        target = server if server is not None else url
        async with Client(target) as client:
            result = await client.call_tool(name, arguments)
            return json.loads(result.content[0].text)

    return anyio.run(go)
