"""One bounded StateGraph. No edge back to routing."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agent.backend import KnowledgeBackend
from agent.llm import ChatModel
from agent.nodes.answer import answer_node
from agent.nodes.remember import remember_node
from agent.nodes.retrieve import retrieve_node
from agent.nodes.route import route_node
from agent.nodes.understand import understand_node
from agent.state.schema import AgentState, TurnResult


def build_graph(
    backend: KnowledgeBackend,
    llm: ChatModel,
    *,
    checkpointer=None,
    data_root: Path | None = None,
):
    saver = checkpointer
    if saver is None and data_root is not None:
        path = Path(data_root) / "index" / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
    if saver is None:
        saver = InMemorySaver()

    graph = StateGraph(AgentState)
    graph.add_node("understand", understand_node(llm))
    graph.add_node("route", route_node(llm))
    graph.add_node("retrieve", retrieve_node(backend))
    graph.add_node("answer", answer_node(llm))
    graph.add_node("remember", remember_node(llm))
    graph.add_node("fail", _fail)
    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", _ok("route"))
    graph.add_conditional_edges("route", _ok("retrieve"))
    graph.add_conditional_edges("retrieve", _ok("answer"))
    graph.add_conditional_edges("answer", _ok("remember"))
    graph.add_edge("remember", END)
    graph.add_edge("fail", END)
    return graph.compile(checkpointer=saver)


def run_turn(
    graph,
    *,
    project_id: str,
    message: str,
    prior_turns: list[dict[str, str]] | None = None,
    thread_id: str = "harbor",
) -> TurnResult:
    state = graph.invoke(
        {
            "project_id": project_id,
            "user_message": message,
            "prior_turns": prior_turns or [],
            "memories": [],
            "chunks": [],
            "trace": [],
            "tool_ok": [],
            "tool_calls": 0,
            "error": None,
        },
        {"configurable": {"thread_id": thread_id}},
    )
    return TurnResult.from_state(state)


def _fail(state: AgentState) -> dict[str, Any]:
    message = state.get("error") or "The turn failed."
    return {
        "answer": message,
        "grounding": "unknown",
        "citations": [],
        "remember_outcome": "skip",
    }


def _ok(success: str):
    def branch(state: AgentState) -> Literal["fail"] | str:
        if state.get("error"):
            return "fail"
        return success

    return branch
