from __future__ import annotations

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
            payload = {"answer": raw or "unknown", "grounding": "unknown", "citations": []}
        text = str(payload.get("answer") or "").strip()
        grounding = str(payload.get("grounding") or "unknown")
        if grounding not in GROUNDING:
            grounding = "unknown"
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
