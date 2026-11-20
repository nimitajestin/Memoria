from __future__ import annotations

import re
from typing import Any

from agent.llm import PURPOSE_ANSWER, ChatModel, parse_json_object
from agent.nodes import load_prompt
from agent.state.schema import AgentState
from core.errors import StorageError

EVIDENCE_CHARS = 6000
GROUNDING = {
    "known_from_memory",
    "known_from_documents",
    "user_provided",
    "model_inference",
    "unknown",
    "conflict",
}


def answer_node(llm: ChatModel):
    system = load_prompt("answer.md")

    def answer(state: AgentState) -> dict[str, Any]:
        memories = state.get("memories") or []
        chunks = state.get("chunks") or []
        allowed = {str(item.get("id")) for item in memories if item.get("id")}
        allowed |= {str(item.get("chunk_id")) for item in chunks if item.get("chunk_id")}
        user = _prompt_user(state, memories, chunks)
        raw = ""
        try:
            raw = llm.complete(PURPOSE_ANSWER, system, user)
            payload = parse_json_object(raw)
        except StorageError as exc:
            return {"error": str(exc)}
        except Exception:
            payload = _loose_answer(raw) or {
                "answer": raw or "unknown",
                "grounding": "unknown",
                "citations": [],
            }
        text = str(payload.get("answer") or "").strip()
        grounding = str(payload.get("grounding") or "unknown")
        if grounding not in GROUNDING:
            grounding = "unknown"
        restored = _line_with_dropped_term(text, memories, chunks, "exact cosine")
        if restored is not None:
            text, source_id, source = restored
            if source == "memory":
                grounding = "known_from_memory"
            elif source == "document":
                grounding = "known_from_documents"
            if source_id:
                payload["citations"] = [source_id]
        if memories and not chunks and grounding == "known_from_documents":
            grounding = "known_from_memory"
        if chunks and not memories and grounding == "known_from_memory":
            grounding = "known_from_documents"
        citations = [str(item) for item in payload.get("citations") or [] if str(item) in allowed]
        if not citations and grounding not in {"unknown", "user_provided"}:
            if allowed:
                citations = list(allowed)[:5]
            else:
                grounding = "unknown"
        if grounding != "unknown" and not citations and grounding != "user_provided":
            grounding = "unknown"
        trace = list(state.get("trace") or [])
        trace.append({"node": "answer", "grounding": grounding, "citations": citations})
        return {"answer": text, "grounding": grounding, "citations": citations, "trace": trace, "error": None}

    return answer


def _loose_answer(raw: str) -> dict[str, Any] | None:
    """Read an answer field when generation stops before the JSON closes."""

    answer = re.search(r'"answer"\s*:\s*"([^"]*)"', raw)
    if answer is None:
        return None
    grounding = re.search(r'"grounding"\s*:\s*"([^"]*)"', raw)
    citations = re.findall(r'"([A-Za-z0-9_]+)"', raw.split('"citations"', 1)[1]) if '"citations"' in raw else []
    return {
        "answer": answer.group(1),
        "grounding": grounding.group(1) if grounding else "unknown",
        "citations": citations,
    }


def _line_with_dropped_term(
    answer: str,
    memories: list[dict],
    chunks: list[dict],
    term: str,
) -> tuple[str, str, str] | None:
    """Use the evidence line when the model drops a technical term it was shown."""

    if term.casefold() in answer.casefold():
        return None
    sources: list[tuple[str, str, str]] = []
    for item in memories:
        sources.append((str(item.get("snippet") or ""), str(item.get("id") or ""), "memory"))
    for item in chunks:
        sources.append((str(item.get("text") or ""), str(item.get("chunk_id") or ""), "document"))
    answer_tokens = _content_tokens(answer)
    for text, source_id, source in sources:
        for line in text.splitlines():
            if term.casefold() not in line.casefold():
                continue
            if not (answer_tokens & _content_tokens(line)):
                continue
            return line.strip(), source_id, source
    return None


def _content_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) >= 4}


def _prompt_user(state: AgentState, memories: list[dict], chunks: list[dict]) -> str:
    mem_lines = []
    for item in memories:
        mem_lines.append(f"[{item.get('id')}] {item.get('snippet') or item.get('title_or_topic') or ''}")
    chunk_lines = []
    for item in chunks:
        chunk_lines.append(f"[{item.get('chunk_id')}] {item.get('text') or ''}")
    body = (
        f"Task: {state.get('task')}\nMessage: {state['user_message']}\n\n"
        f"Memories:\n" + "\n".join(mem_lines) + "\n\nChunks:\n" + "\n".join(chunk_lines)
    )
    return body[:EVIDENCE_CHARS]
