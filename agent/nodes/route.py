from __future__ import annotations

from typing import Any

from agent.llm import PURPOSE_ROUTE, ChatModel, parse_json_object, route_from_text
from agent.nodes import load_prompt
from agent.state.schema import AgentState
from core.errors import StorageError

ALLOWED = {"none", "memory", "documents", "both"}


def route_node(llm: ChatModel):
    system = load_prompt("route.md")

    def route(state: AgentState) -> dict[str, Any]:
        user = f"Task: {state.get('task')}\nQuery: {state.get('query')}\nMessage: {state['user_message']}"
        try:
            raw = llm.complete(PURPOSE_ROUTE, system, user)
            payload = parse_json_object(raw)
            label = str(payload.get("route") or "").strip()
            reason = str(payload.get("reason") or "")[:200]
            if label not in ALLOWED:
                label, reason = route_from_text(user)
            trace = list(state.get("trace") or [])
            trace.append({"node": "route", "route": label, "reason": reason})
            return {"route": label, "route_reason": reason, "trace": trace, "error": None}
        except StorageError as exc:
            return {"error": str(exc)}
        except Exception:
            label, reason = route_from_text(user)
            trace = list(state.get("trace") or [])
            trace.append({"node": "route", "route": label, "reason": reason})
            return {"route": label, "route_reason": reason, "trace": trace, "error": None}

    return route
