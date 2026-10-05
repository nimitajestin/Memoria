"""System B: same graph as C, memory and documents through core, no MCP process."""

from __future__ import annotations

from typing import Any

from agent.graph.build import build_graph, run_turn
from agent.llm import ChatModel
from agent.state.schema import TurnResult
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from ingestion.embedding.batch import Embedder


class DirectBackend:
    def __init__(self, memory: MemoryRepository, documents: DocumentRepository, embedder: Embedder) -> None:
        self.memory = memory
        self.documents = documents
        self.embedder = embedder

    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.memory.search(project_id, query, limit=limit)]

    def search_documents(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        hits = search_documents(self.documents, project_id, query, self.embedder, limit=limit)
        return [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "text": item.text,
                "retrieval_score": item.retrieval_score,
                "location": item.location.model_dump(mode="json") if item.location else None,
            }
            for item in hits
        ]


def run_direct(
    *,
    project_id: str,
    message: str,
    memory: MemoryRepository,
    documents: DocumentRepository,
    embedder: Embedder,
    llm: ChatModel,
    prior_turns: list[dict[str, str]] | None = None,
    thread_id: str = "harbor-b",
) -> TurnResult:
    graph = build_graph(DirectBackend(memory, documents, embedder), llm)
    return run_turn(
        graph,
        project_id=project_id,
        message=message,
        prior_turns=prior_turns,
        thread_id=thread_id,
    )
