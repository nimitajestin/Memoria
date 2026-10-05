from pathlib import Path

from core.retrieval.hash_embedder import HashEmbedder
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from evaluation.datasets.controlled.load import HARBOR, load_harbor, load_questions
from evaluation.experiments.vector_gate import gold_chunk_ids
from evaluation.metrics.retrieval import mrr, precision_at_k, recall_at_k
from ingestion.indexing.pipeline import index_project


def test_direct_retrieval_recall_on_harbor(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    store = DocumentRepository(tmp_path)
    try:
        questions = [item for item in load_questions() if item.category == "direct_retrieval"]
        assert questions
        recalls = []
        for item in questions:
            gold = gold_chunk_ids(store, HARBOR, item.gold_markers)
            assert gold
            hits = search_documents(store, HARBOR, item.question, embedder)
            ranked = [hit.chunk_id or "" for hit in hits]
            recalls.append(recall_at_k(gold, ranked, 5))
            assert hits[0].source == "document"
            assert hits[0].location is not None
            assert hits[0].location.filename
            assert 0.0 <= hits[0].retrieval_score <= 1.0 or hits[0].retrieval_score <= 1.0001
        assert min(recalls) == 1.0
        sample = search_documents(store, HARBOR, questions[0].question, embedder)
        gold = gold_chunk_ids(store, HARBOR, questions[0].gold_markers)
        ranked = [hit.chunk_id or "" for hit in sample]
        assert precision_at_k(gold, ranked, 5) > 0
        assert mrr(gold, ranked) == 1.0
    finally:
        store.close()


def test_search_can_filter_by_document(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    store = DocumentRepository(tmp_path)
    try:
        hits = search_documents(
            store,
            HARBOR,
            "Harbor workstation RAM",
            embedder,
            document_id="doc_aa0000000001",
        )
        assert hits
        assert all(hit.document_id == "doc_aa0000000001" for hit in hits)
    finally:
        store.close()
