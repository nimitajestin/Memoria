"""Batch embedding writes. Bound is 8 chunks."""

from __future__ import annotations

from typing import Protocol

from core.schemas.documents import ChunkRecord
from core.storage.documents import DocumentRepository

BATCH = 8


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def embed_chunks(
    store: DocumentRepository,
    project_id: str,
    chunks: list[ChunkRecord],
    embedder: Embedder,
    batch_size: int = BATCH,
) -> None:
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embedder.embed([item.text for item in batch])
        if len(vectors) != len(batch):
            from core.errors import StorageError

            raise StorageError("FAILED_DEPENDENCY", "Embedding batch size mismatch.")
        for chunk, vector in zip(batch, vectors, strict=True):
            store.put_embedding(project_id, chunk.id, embedder.model, vector)
        del vectors
        del batch
