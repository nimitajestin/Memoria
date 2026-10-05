"""System A: embed, top-k chunks, one chat call. No memory, no MCP, no routing."""

from __future__ import annotations

from agent.llm import PURPOSE_ANSWER, ChatModel, parse_json_object
from agent.nodes.answer import EVIDENCE_CHARS, GROUNDING
from agent.state.schema import TurnResult
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from ingestion.embedding.batch import Embedder


def run_stateless(
    *,
    project_id: str,
    message: str,
    documents: DocumentRepository,
    embedder: Embedder,
    llm: ChatModel,
    prior_turns: list[dict[str, str]] | None = None,
) -> TurnResult:
    del prior_turns
    hits = search_documents(documents, project_id, message, embedder, limit=5)
    chunks = [
        {
            "chunk_id": item.chunk_id,
            "document_id": item.document_id,
            "text": item.text,
            "retrieval_score": item.retrieval_score,
            "location": item.location.model_dump(mode="json") if item.location else None,
        }
        for item in hits
    ]
    allowed = {str(item["chunk_id"]) for item in chunks if item.get("chunk_id")}
    lines = "\n".join(f"[{item['chunk_id']}] {item.get('text') or ''}" for item in chunks)
    user = f"Task: {message}\nMessage: {message}\n\nMemories:\n\nChunks:\n{lines}"[:EVIDENCE_CHARS]
    try:
        payload = parse_json_object(llm.complete(PURPOSE_ANSWER, "Answer from chunks only.", user))
    except Exception:
        payload = {"answer": "unknown", "grounding": "unknown", "citations": []}
    citations = [str(item) for item in payload.get("citations") or [] if str(item) in allowed]
    grounding = str(payload.get("grounding") or "unknown")
    if grounding not in GROUNDING:
        grounding = "unknown"
    if not citations and grounding not in {"unknown", "user_provided"}:
        grounding = "unknown" if not allowed else "known_from_documents"
        citations = list(allowed)[:5] if grounding != "unknown" else []
    return TurnResult(
        answer=str(payload.get("answer") or ""),
        grounding=grounding,
        citations=citations,
        route=None,
        chunks=chunks,
        tool_ok=[True],
        trace=[{"node": "stateless_rag", "chunk_ids": list(allowed)}],
        remember_outcome="skip",
    )
