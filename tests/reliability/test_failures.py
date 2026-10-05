from pathlib import Path

from agent.graph.build import build_graph, run_turn
from agent.llm import HeuristicChat
from agent.mcp_client import MCPBackend
from core.retrieval.hash_embedder import HashEmbedder
from core.retrieval.search import search_documents
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from ingestion.indexing.pipeline import index_project
from ingestion.indexing.rebuild import rebuild_index


def test_rebuild_after_sqlite_is_removed(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    sqlite = tmp_path / "index" / "memoria.sqlite"
    sqlite.unlink()
    wal = tmp_path / "index" / "memoria.sqlite-wal"
    shm = tmp_path / "index" / "memoria.sqlite-shm"
    if wal.exists():
        wal.unlink()
    if shm.exists():
        shm.unlink()
    report = rebuild_index(tmp_path, embedder)
    assert report.reindexed >= 8
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    hits = search_documents(documents, HARBOR, "Harbor RAM", embedder, limit=5)
    assert hits
    records = memory.list_records(HARBOR, types=["decision"])
    assert any(item.id == "decision_a11ce0000001" for item in records)
    memory.close()


def test_system_c_mcp_down_does_not_write_memory(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    before = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    result = run_turn(
        build_graph(MCPBackend(url="http://127.0.0.1:1/mcp"), HeuristicChat()),
        project_id=HARBOR,
        message="What architecture did I decide for the retrieval system?",
        thread_id="mcp-down",
    )
    assert result.error
    assert "MCP" in (result.answer or "")
    after = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    assert before == after
