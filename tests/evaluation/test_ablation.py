from pathlib import Path

from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import DirectBackend
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from evaluation.experiments.ablation import render_ablation, run_ablation
from ingestion.indexing.pipeline import index_project


def test_ablation_modes_change_what_is_retrieved(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    query = "What architecture did I decide for the retrieval system?"
    conv = DirectBackend(memory, documents, embedder, ablation="conversations")
    structured = DirectBackend(memory, documents, embedder, ablation="structured")
    full = DirectBackend(memory, documents, embedder, ablation="full")
    assert conv.search_documents(HARBOR, query) == []
    assert structured.search_documents(HARBOR, query) == []
    assert full.search_documents(HARBOR, query)
    mem_hits = structured.search_memory(HARBOR, query)
    assert any(item["id"] == "decision_a11ce0000001" for item in mem_hits)
    memory.close()


def test_offline_ablation_report(tmp_path: Path) -> None:
    result = run_ablation(tmp_path, question_ids=["q01", "q07"])
    markdown = render_ablation(result)
    assert "| A |" in markdown
    assert "| E |" in markdown
    assert "Interpretation" in markdown
