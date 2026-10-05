"""Exact cosine search over SQLite float32 blobs."""

from __future__ import annotations

import heapq

import numpy as np

from core.schemas.evidence import EvidenceItem, EvidenceLocation
from core.schemas.memory import utc_now
from core.storage.documents import DocumentRepository
from ingestion.embedding.batch import Embedder

DEFAULT_K = 5
BATCH = 64


def search_documents(
    store: DocumentRepository,
    project_id: str,
    query: str,
    embedder: Embedder,
    *,
    limit: int = DEFAULT_K,
    document_id: str | None = None,
    file_type: str | None = None,
) -> list[EvidenceItem]:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        from core.errors import StorageError

        raise StorageError("VALIDATION", "Search query must be 1 to 1000 characters.")
    if limit < 1 or limit > DEFAULT_K:
        from core.errors import StorageError

        raise StorageError("VALIDATION", "Search limit must be from 1 to 5.")
    vectors = embedder.embed([query.strip()])
    query_vec = np.asarray(vectors[0], dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vec))
    if query_norm == 0.0:
        return []
    query_vec = query_vec / query_norm
    heap: list[tuple[float, int, dict]] = []
    tie = 0
    for row in store.index.iter_search_rows(
        project_id,
        document_id=document_id,
        file_type=file_type,
        batch_size=BATCH,
    ):
        blob = row["vector"]
        dimension = int(row["dimension"])
        if len(blob) != dimension * 4:
            continue
        vector = np.frombuffer(blob, dtype="<f4")
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            continue
        score = float(np.dot(vector / norm, query_vec))
        item = (score, tie, row)
        tie += 1
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif score > heap[0][0]:
            heapq.heapreplace(heap, item)
        del vector
    ranked = sorted(heap, key=lambda item: (-item[0], item[1]))
    retrieved_at = utc_now()
    evidence: list[EvidenceItem] = []
    for score, _tie, row in ranked:
        evidence.append(
            EvidenceItem(
                source="document",
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                memory_id=None,
                location=EvidenceLocation(
                    filename=row["filename"],
                    section=row["section"],
                    page=row["page"],
                    line_start=row["line_start"],
                    line_end=row["line_end"],
                ),
                retrieval_score=round(score, 6),
                retrieved_at=retrieved_at,
                text=row["text"],
            )
        )
    return evidence
