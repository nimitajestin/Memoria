"""Remember node. Phase 5 records a skip; writes land in Phase 6."""

from __future__ import annotations

from typing import Any

from agent.llm import PURPOSE_REMEMBER, ChatModel
from agent.nodes import load_prompt
from agent.state.schema import AgentState


def remember_node(llm: ChatModel):
    system = load_prompt("candidates.md")

    def remember(state: AgentState) -> dict[str, Any]:
        user = f"Message: {state['user_message']}\nAnswer: {state.get('answer') or ''}"
        try:
            llm.complete(PURPOSE_REMEMBER, system, user)
        except Exception:
            pass
        trace = list(state.get("trace") or [])
        trace.append({"node": "remember", "outcome": "skip"})
        return {"remember_outcome": "skip", "trace": trace}

    return remember
