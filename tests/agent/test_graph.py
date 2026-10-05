from pathlib import Path

from agent.graph.build import build_graph, run_turn
from agent.llm import HeuristicChat
from agent.mcp_client import MCPBackend
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import DirectBackend, run_direct
from evaluation.baselines.stateless_rag import run_stateless
from evaluation.datasets.controlled.load import HARBOR
from evaluation.metrics.agent import score_item
from tests.agent.conftest import harbor_stack


def test_system_a_has_no_memory_or_route(tmp_path: Path) -> None:
    _loaded, embedder, questions, _server = harbor_stack(tmp_path)
    item = questions["q07"]
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    result = run_stateless(
        project_id=HARBOR,
        message=item.question,
        documents=documents,
        embedder=embedder,
        llm=HeuristicChat(),
    )
    assert result.route is None
    assert result.memories == []
    assert result.chunks
    memory.close()


def test_systems_b_and_c_match_gold_routes_on_harbor(tmp_path: Path) -> None:
    loaded, embedder, questions, server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    llm = HeuristicChat()
    sample = [questions["q01"], questions["q07"], questions["q13"], questions["q18"]]
    for item in sample:
        b = run_direct(
            project_id=HARBOR,
            message=item.question,
            memory=memory,
            documents=documents,
            embedder=embedder,
            llm=llm,
            prior_turns=[turn.model_dump() for turn in item.prior_turns],
            thread_id=f"b-{item.id}",
        )
        c_graph = build_graph(MCPBackend(server=server), llm)
        c = run_turn(
            c_graph,
            project_id=HARBOR,
            message=item.question,
            prior_turns=[turn.model_dump() for turn in item.prior_turns],
            thread_id=f"c-{item.id}",
        )
        b_score = score_item(item, b, "B")
        c_score = score_item(item, c, "C")
        assert b_score.route_ok is True, (item.id, b.route)
        assert c_score.route_ok is True, (item.id, c.route)
        if item.gold_memory_ids:
            assert {row.get("id") for row in b.memories} & set(item.gold_memory_ids)
            assert {row.get("id") for row in c.memories} & set(item.gold_memory_ids)
        assert b.remember_outcome == "skip"
        assert c.remember_outcome == "skip"
        assert all(c.tool_ok)
    memory.close()


def test_system_c_mcp_down_is_a_failure(tmp_path: Path) -> None:
    llm = HeuristicChat()
    graph = build_graph(MCPBackend(url="http://127.0.0.1:1/mcp"), llm)
    result = run_turn(graph, project_id=HARBOR, message="What architecture did I decide?", thread_id="down")
    assert result.error
    assert "MCP" in (result.answer or result.error)


def test_remember_does_not_write_yaml(tmp_path: Path) -> None:
    _loaded, embedder, questions, _server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    before = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    run_direct(
        project_id=HARBOR,
        message=questions["q08"].question,
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=HeuristicChat(),
        thread_id="remember-skip",
    )
    after = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    assert before == after
    memory.close()


def test_sqlite_checkpointer_round_trip(tmp_path: Path) -> None:
    _loaded, embedder, _questions, _server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    backend = DirectBackend(memory, documents, embedder)
    graph = build_graph(backend, HeuristicChat(), data_root=tmp_path)
    first = run_turn(graph, project_id=HARBOR, message="What architecture did I decide?", thread_id="ckpt")
    assert first.route == "memory"
    assert (tmp_path / "index" / "checkpoints.sqlite").exists()
    memory.close()
