"""Remember node. The model proposes; policy disposes; at most one write."""

from __future__ import annotations

from typing import Any

from agent.backend import KnowledgeBackend
from agent.llm import PURPOSE_REMEMBER, ChatModel, parse_json_object
from agent.nodes import load_prompt
from agent.state.schema import AgentState
from core.errors import StorageError
from core.memory.policy import evaluate


def remember_node(llm: ChatModel, backend: KnowledgeBackend):
    system = load_prompt("candidates.md")

    def remember(state: AgentState) -> dict[str, Any]:
        message = state["user_message"].strip()
        user = f"Message: {message}\nAnswer: {state.get('answer') or ''}"
        outcomes: list[dict[str, Any]] = []
        wrote = False
        # A question does not propose a durable memory. Skipping the model here
        # keeps a recall turn to the calls that choose and word the answer.
        if message.endswith("?") and "remember" not in message.casefold():
            payload = {"candidates": []}
        else:
            try:
                raw = llm.complete(PURPOSE_REMEMBER, system, user)
                payload = parse_json_object(raw)
            except Exception:
                payload = {"candidates": []}
        candidates = list(payload.get("candidates") or [])[:2]
        existing = []
        try:
            existing = backend.policy_records(state["project_id"])
        except Exception:
            existing = []
        for candidate in candidates:
            result = evaluate(candidate, existing)
            entry = {"outcome": result.outcome, "reason": result.reason, "detail": result.detail}
            if wrote or result.outcome == "reject":
                outcomes.append(entry)
                continue
            try:
                stored = _write(backend, state["project_id"], candidate, result)
                entry["id"] = stored.get("id")
                wrote = True
            except StorageError as exc:
                entry = {"outcome": "reject", "reason": exc.code, "detail": str(exc)}
            outcomes.append(entry)
        summary = outcomes[0]["outcome"] if outcomes else "skip"
        if not candidates:
            summary = "skip"
        trace = list(state.get("trace") or [])
        trace.append({"node": "remember", "outcome": summary, "candidates": outcomes})
        return {"remember_outcome": summary, "trace": trace}

    return remember


def _write(backend: KnowledgeBackend, project_id: str, candidate: dict, result) -> dict[str, Any]:
    if result.outcome == "update" and result.target_id:
        patch = _content_fields(candidate)
        expected = next((item.revision for item in backend.policy_records(project_id) if item.id == result.target_id), 1)
        return backend.update_memory(project_id, result.target_id, patch, expected)
    payload = _create_payload(candidate, result.conflict_ids)
    return backend.create_memory(project_id, payload)


def _create_payload(candidate: dict, conflict_ids: list[str]) -> dict[str, Any]:
    kind = candidate.get("type")
    source = {"kind": candidate.get("source_kind") or "user", "ref": None, "quote": None}
    refs = candidate.get("evidence_refs") or []
    if refs:
        source["ref"] = refs[0]
    payload: dict[str, Any] = {
        "type": kind,
        "source": source,
        "created_by": "agent",
        "conflicts_with": list(conflict_ids or []),
    }
    for key in (
        "topic",
        "statement",
        "decision",
        "reason",
        "title",
        "body",
        "tags",
        "goal_status",
        "summary",
        "occurred_at",
        "conversation_id",
        "phase",
        "blockers",
        "supersedes",
        "confidence",
    ):
        if candidate.get(key) is not None:
            payload[key] = candidate[key]
    return payload


def _content_fields(candidate: dict) -> dict[str, Any]:
    skip = {
        "type",
        "confidence",
        "stable",
        "project_specific",
        "future_useful",
        "evidence_refs",
        "source_kind",
        "supersedes",
    }
    return {key: value for key, value in candidate.items() if key not in skip and value is not None}
