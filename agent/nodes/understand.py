from __future__ import annotations

from typing import Any

from agent.llm import PURPOSE_UNDERSTAND, ChatModel, parse_json_object
from agent.nodes import load_prompt
from agent.state.schema import AgentState
from core.errors import StorageError


def understand_node(llm: ChatModel):
    system = load_prompt("understand.md")

    def understand(state: AgentState) -> dict[str, Any]:
        message = state["user_message"].strip()
        if len(message) <= 200 and message.endswith("?") and not (state.get("prior_turns") or []):
            trace = list(state.get("trace") or [])
            trace.append({"node": "understand", "task": message, "query": message})
            return {"task": message, "query": message, "trace": trace, "error": None}
        prior = state.get("prior_turns") or []
        lines = [f"{item.get('role')}: {item.get('content')}" for item in prior]
        user = "Prior:\n" + "\n".join(lines) + "\n\nMessage:\n" + message
        try:
            raw = llm.complete(PURPOSE_UNDERSTAND, system, user)
            payload = parse_json_object(raw)
            task = str(payload.get("task") or state["user_message"]).strip()
            query = str(payload.get("query") or task).strip()[:200]
            trace = list(state.get("trace") or [])
            trace.append({"node": "understand", "task": task, "query": query})
            return {"task": task, "query": query, "trace": trace, "error": None}
        except StorageError as exc:
            return {"error": str(exc)}
        except Exception:
            task = state["user_message"]
            trace = list(state.get("trace") or [])
            trace.append({"node": "understand", "task": task, "query": task})
            return {"task": task, "query": task, "trace": trace, "error": None}

    return understand
