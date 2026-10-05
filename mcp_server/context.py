"""Shared vault handles for one MCP server process."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from ingestion.embedding.batch import Embedder


@dataclass
class ServerContext:
    root: Path
    memory: MemoryRepository
    documents: DocumentRepository
    embedder: Embedder

    def close(self) -> None:
        self.documents.close()
        self.memory.close()


def open_context(data_root: Path, embedder: Embedder | None = None) -> ServerContext:
    root = Path(data_root).resolve()
    memory = MemoryRepository(root)
    documents = DocumentRepository(root, memory.index)
    return ServerContext(
        root=root,
        memory=memory,
        documents=documents,
        embedder=embedder or HashEmbedder(),
    )
