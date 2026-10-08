"""System B: same graph as C, memory and documents through core, no MCP process."""

from __future__ import annotations

from typing import Any, Literal

from agent.graph.build import build_graph, run_turn
from agent.llm import ChatModel
from agent.state.schema import TurnResult
from core.memory.content import fingerprint
from core.memory.policy import PolicyRecord
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from ingestion.embedding.batch import Embedder

Ablation = Literal["full", "conversations", "structured", "structured_episodic"]
STRUCTURED_TYPES = ["fact", "decision", "goal", "knowledge", "status"]
EPISODIC_TYPES = ["episode", "conversation_summary"]


class DirectBackend:
    def __init__(
        self,
        memory: MemoryRepository,
        documents: DocumentRepository,
        embedder: Embedder,
        *,
        ablation: Ablation = "full",
    ) -> None:
        self.memory = memory
        self.documents = documents
        self.embedder = embedder
        self.ablation = ablation

    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if self.ablation == "conversations":
            return self._search_conversations(project_id, query, limit)
        types = None
        if self.ablation == "structured":
            types = STRUCTURED_TYPES
        elif self.ablation == "structured_episodic":
            types = STRUCTURED_TYPES + EPISODIC_TYPES
        return [item.model_dump(mode="json") for item in self.memory.search(project_id, query, types=types, limit=limit)]

    def search_documents(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if self.ablation in {"conversations", "structured", "structured_episodic"}:
            return []
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

    def policy_records(self, project_id: str) -> list[PolicyRecord]:
        records = self.memory.list_records(project_id, status="active")
        snapshots: list[PolicyRecord] = []
        for record in records:
            digest, identity, topic = fingerprint(record.type, record.model_dump())
            snapshots.append(
                PolicyRecord(
                    record.id,
                    record.type,
                    topic,
                    digest,
                    identity,
                    record.revision,
                    record.status,
                )
            )
        return snapshots

    def create_memory(self, project_id: str, record: dict[str, Any]) -> dict[str, Any]:
        stored = self.memory.create_record(project_id, record)
        return stored.model_dump(mode="json")

    def update_memory(
        self,
        project_id: str,
        record_id: str,
        patch: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        stored = self.memory.update_record(project_id, record_id, patch, expected_revision)
        return stored.model_dump(mode="json")

    def _search_conversations(self, project_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        directory = self.memory.root / "conversations" / project_id
        if not directory.exists():
            return []
        tokens = [token for token in query.casefold().split() if token]
        hits: list[dict[str, Any]] = []
        for path in sorted(directory.glob("conv_*.json")):
            try:
                conversation = self.memory.conversations.load(project_id, path.stem)
            except Exception:
                continue
            for index, turn in enumerate(conversation.turns):
                haystack = turn.content.casefold()
                matched = sum(1 for token in tokens if token in haystack)
                if matched == 0:
                    continue
                hits.append(
                    {
                        "id": f"{conversation.id}:{index}",
                        "type": "conversation_turn",
                        "title_or_topic": conversation.title,
                        "score": round(matched / max(len(tokens), 1), 4),
                        "snippet": turn.content[:400],
                        "updated_at": conversation.created_at,
                    }
                )
        hits.sort(key=lambda item: (-item["score"], item["id"]))
        return hits[:limit]


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
    ablation: Ablation = "full",
) -> TurnResult:
    graph = build_graph(DirectBackend(memory, documents, embedder, ablation=ablation), llm)
    return run_turn(
        graph,
        project_id=project_id,
        message=message,
        prior_turns=prior_turns,
        thread_id=thread_id,
    )
