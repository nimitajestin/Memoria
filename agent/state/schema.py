"""Typed graph state. Short traces only; no corpus blobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

Route = Literal["none", "memory", "documents", "both"]
Grounding = Literal[
    "known_from_memory",
    "known_from_documents",
    "user_provided",
    "model_inference",
    "unknown",
    "conflict",
]


class AgentState(TypedDict, total=False):
    project_id: str
    user_message: str
    prior_turns: list[dict[str, str]]
    task: str
    query: str
    route: Route
    route_reason: str
    memories: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    answer: str
    grounding: str
    citations: list[str]
    error: str | None
    trace: list[dict[str, Any]]
    tool_calls: int
    tool_ok: list[bool]
    remember_outcome: str


@dataclass
class TurnResult:
    answer: str
    grounding: str
    citations: list[str]
    route: str | None
    memories: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    tool_ok: list[bool] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    remember_outcome: str = "skip"

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> TurnResult:
        return cls(
            answer=str(state.get("answer") or ""),
            grounding=str(state.get("grounding") or "unknown"),
            citations=list(state.get("citations") or []),
            route=state.get("route"),
            memories=list(state.get("memories") or []),
            chunks=list(state.get("chunks") or []),
            error=state.get("error"),
            tool_ok=list(state.get("tool_ok") or []),
            trace=list(state.get("trace") or []),
            remember_outcome=str(state.get("remember_outcome") or "skip"),
        )
