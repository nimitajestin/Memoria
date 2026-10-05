from __future__ import annotations

from typing import Any

from agent.backend import KnowledgeBackend
from agent.mcp_client import MCPUnavailable
from agent.state.schema import AgentState
from core.errors import StorageError


def retrieve_node(backend: KnowledgeBackend):
    def retrieve(state: AgentState) -> dict[str, Any]:
        route = state.get("route") or "none"
        query = state.get("query") or state["user_message"]
        project_id = state["project_id"]
        memories: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        tool_ok = list(state.get("tool_ok") or [])
        try:
            if route in {"memory", "both"}:
                memories = _once(lambda: backend.search_memory(project_id, query), tool_ok)
            if route in {"documents", "both"}:
                chunks = _once(lambda: backend.search_documents(project_id, query), tool_ok)
        except MCPUnavailable as exc:
            return {"error": f"MCP-unavailable: {exc}", "tool_ok": tool_ok}
        except StorageError as exc:
            return {"error": str(exc), "tool_ok": tool_ok}
        trace = list(state.get("trace") or [])
        trace.append(
            {
                "node": "retrieve",
                "memory_ids": [item.get("id") for item in memories],
                "chunk_ids": [item.get("chunk_id") for item in chunks],
            }
        )
        calls = state.get("tool_calls") or 0
        return {
            "memories": memories[:5],
            "chunks": chunks[:5],
            "tool_ok": tool_ok,
            "tool_calls": calls + len(tool_ok),
            "trace": trace,
            "error": None,
        }

    return retrieve


def _once(action, tool_ok: list[bool]):
    try:
        value = action()
        tool_ok.append(True)
        return value
    except Exception:
        try:
            value = action()
            tool_ok.append(True)
            return value
        except Exception:
            tool_ok.append(False)
            raise
