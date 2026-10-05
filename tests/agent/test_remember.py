import json
from pathlib import Path

from agent.graph.build import build_graph, run_turn
from agent.llm import PURPOSE_REMEMBER, HeuristicChat
from agent.mcp_client import MCPBackend
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import run_direct
from evaluation.datasets.controlled.load import HARBOR
from tests.agent.conftest import harbor_stack


class ScriptedChat(HeuristicChat):
    def __init__(self, candidates: list[dict]) -> None:
        self.candidates = candidates

    def complete(self, purpose: str, system: str, user: str) -> str:
        if purpose == PURPOSE_REMEMBER:
            return json.dumps({"candidates": self.candidates})
        return super().complete(purpose, system, user)


def _fact(statement: str, **overrides) -> dict:
    payload = {
        "type": "fact",
        "confidence": 0.9,
        "stable": True,
        "project_specific": True,
        "future_useful": True,
        "source_kind": "user",
        "topic": "notes",
        "statement": statement,
    }
    payload.update(overrides)
    return payload


def test_remember_creates_one_durable_fact(tmp_path: Path) -> None:
    _loaded, embedder, _questions, _server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    before = list((tmp_path / "memory" / "projects" / HARBOR / "facts").glob("*.yaml"))
    result = run_direct(
        project_id=HARBOR,
        message="Please remember that Harbor tests run on CPU only.",
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=ScriptedChat([_fact("Harbor tests run on CPU only.")]),
        thread_id="create-fact",
    )
    after = list((tmp_path / "memory" / "projects" / HARBOR / "facts").glob("*.yaml"))
    assert result.remember_outcome == "create"
    assert len(after) == len(before) + 1
    memory.close()


def test_remember_rejects_low_confidence_without_write(tmp_path: Path) -> None:
    _loaded, embedder, _questions, _server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    before = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    result = run_direct(
        project_id=HARBOR,
        message="Maybe the mascot is a seal.",
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=ScriptedChat([_fact("The mascot is a seal.", confidence=0.4)]),
        thread_id="low-conf",
    )
    after = sorted(path.read_bytes() for path in (tmp_path / "memory").rglob("*.yaml"))
    assert result.remember_outcome == "reject"
    assert before == after
    memory.close()


def test_remember_rejects_duplicate_and_decision_overwrite(tmp_path: Path) -> None:
    _loaded, embedder, _questions, _server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    duplicate = run_direct(
        project_id=HARBOR,
        message="The Harbor workstation has 8 GB of RAM and no discrete GPU.",
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=ScriptedChat(
            [_fact("The Harbor workstation has 8 GB of RAM and no discrete GPU.", topic="hardware")]
        ),
        thread_id="dup",
    )
    assert duplicate.remember_outcome == "reject"
    decision = {
        "type": "decision",
        "confidence": 0.95,
        "stable": True,
        "project_specific": True,
        "future_useful": True,
        "source_kind": "user",
        "topic": "vector_storage",
        "decision": "Use a vector database.",
        "reason": "It might be faster.",
    }
    path = tmp_path / "memory" / "projects" / HARBOR / "decisions" / "decision_a11ce0000001.yaml"
    before = path.read_bytes()
    overwritten = run_direct(
        project_id=HARBOR,
        message="Switch retrieval to a vector database.",
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=ScriptedChat([decision]),
        thread_id="dec",
    )
    assert overwritten.remember_outcome == "reject"
    assert path.read_bytes() == before
    memory.close()


def test_remember_conflict_keeps_both_facts_and_writes_once(tmp_path: Path) -> None:
    _loaded, embedder, _questions, server = harbor_stack(tmp_path)
    memory = MemoryRepository(tmp_path)
    documents = DocumentRepository(tmp_path, memory.index)
    before = list((tmp_path / "memory" / "projects" / HARBOR / "facts").glob("*.yaml"))
    candidates = [
        _fact("Harbor standup is 18:00 UTC.", topic="standup"),
        _fact("Harbor also has a night standup.", topic="standup-night"),
    ]
    result = run_direct(
        project_id=HARBOR,
        message="Standup might be 18:00 UTC.",
        memory=memory,
        documents=documents,
        embedder=embedder,
        llm=ScriptedChat(candidates),
        thread_id="conflict",
    )
    after = list((tmp_path / "memory" / "projects" / HARBOR / "facts").glob("*.yaml"))
    assert result.remember_outcome == "create"
    assert len(after) == len(before) + 1
    c = run_turn(
        build_graph(MCPBackend(server=server), ScriptedChat([_fact("Harbor CI uses one local Ollama host.")])),
        project_id=HARBOR,
        message="Remember that Harbor CI uses one local Ollama host.",
        thread_id="c-create",
    )
    assert c.remember_outcome == "create"
    memory.close()
