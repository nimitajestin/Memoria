"""Decide whether exact cosine stays the index. Does not add extra services."""

from __future__ import annotations

from pathlib import Path
from statistics import median
from time import perf_counter

from core.retrieval.hash_embedder import HashEmbedder
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from evaluation.datasets.controlled.load import HARBOR, load_harbor, load_questions
from evaluation.metrics.retrieval import macro_mean, recall_at_k
from ingestion.indexing.pipeline import index_project

LATENCY_BAR_MS = 200.0
K = 5


def gold_chunk_ids(store: DocumentRepository, project_id: str, markers: list[str]) -> list[str]:
    ids: list[str] = []
    for row in store.list_chunks(project_id):
        if any(marker in row["text"] for marker in markers):
            ids.append(row["id"])
    return ids


def run_exact_cosine_gate(data_root: Path) -> dict:
    load_harbor(data_root)
    embedder = HashEmbedder()
    index_project(data_root, HARBOR, embedder=embedder)
    store = DocumentRepository(data_root)
    try:
        questions = [item for item in load_questions() if item.category == "direct_retrieval"]
        recalls: list[float] = []
        latencies: list[float] = []
        for item in questions:
            gold = gold_chunk_ids(store, HARBOR, item.gold_markers)
            started = perf_counter()
            hits = search_documents(store, HARBOR, item.question, embedder, limit=K)
            latencies.append((perf_counter() - started) * 1000)
            recalls.append(recall_at_k(gold, [hit.chunk_id or "" for hit in hits], K))
        median_ms = float(median(latencies)) if latencies else 0.0
        recall = macro_mean(recalls)
        keep_exact = median_ms < LATENCY_BAR_MS
        return {
            "candidate": "sqlite_float32_exact_cosine",
            "recall_at_5": recall,
            "median_latency_ms": median_ms,
            "latency_bar_ms": LATENCY_BAR_MS,
            "sqlite_vec_loaded": _module_available("sqlite_vec"),
            "hnswlib_loaded": _module_available("hnswlib"),
            "selected": "sqlite_float32_exact_cosine" if keep_exact else "needs_ann_followup",
            "keep_exact": keep_exact,
        }
    finally:
        store.close()


def render_gate_report(result: dict) -> str:
    lines = [
        "# Vector search gate",
        "",
        "Phase 4 measurement on the Harbor controlled corpus.",
        "",
        f"- Candidate measured: `{result['candidate']}`",
        f"- Recall@5 (direct retrieval): {result['recall_at_5']:.3f}",
        f"- Median search latency: {result['median_latency_ms']:.2f} ms",
        f"- Latency bar: {result['latency_bar_ms']:.0f} ms",
        f"- sqlite-vec importable: {result['sqlite_vec_loaded']}",
        f"- hnswlib importable: {result['hnswlib_loaded']}",
        f"- Selected: `{result['selected']}`",
        "",
        "sqlite-vec and hnswlib are not adopted unless exact cosine misses the latency bar.",
        "FAISS, LanceDB, Qdrant, PostgreSQL, and Redis stay out of the gate.",
        "",
        "Live Ollama embeddings are optional (`pytest -m ollama`). This gate uses the",
        "deterministic hash embedder so it runs offline.",
        "",
    ]
    return "\n".join(lines)


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except Exception:
        return False
    return True
