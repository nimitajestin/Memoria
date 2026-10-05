from collections import Counter
from pathlib import Path

from core.memory.content import searchable_text
from core.memory.policy import evaluate
from evaluation.datasets.controlled.load import (
    DECOY,
    HARBOR,
    load_harbor,
    load_not_durable_candidate,
    load_questions,
)


def test_not_durable_candidate_is_rejected() -> None:
    result = evaluate(load_not_durable_candidate(), [])
    assert result.outcome == "reject"
    assert result.reason == "not_durable"


def test_questions_cover_required_classes() -> None:
    questions = load_questions()
    assert len(questions) == 24
    counts = Counter(item.category for item in questions)
    required = {
        "direct_retrieval",
        "cross_document",
        "memory_recall",
        "temporal",
        "conflict",
        "irrelevant_rejection",
        "multi_turn",
        "cross_session",
    }
    for category in required:
        assert counts[category] >= 2
    assert counts["import_recall"] >= 1
    ids = [item.id for item in questions]
    assert len(ids) == len(set(ids))


def test_load_harbor_seeds_vault_and_keeps_project_boundary(tmp_path: Path) -> None:
    result = load_harbor(tmp_path)
    from core.storage.memory_repo import MemoryRepository

    repo = MemoryRepository(tmp_path)
    try:
        sqlite = repo.get_record(HARBOR, "decision_a11ce0000001")
        old = repo.get_record(HARBOR, "decision_01d000000002")
        assert sqlite.status == "active"
        assert "SQLite" in sqlite.decision
        assert old.status == "superseded"
        assert old.decision == "Use Qdrant as the Harbor retrieval store."
        assert sqlite.supersedes == old.id
        first = repo.get_record(HARBOR, "fact_c0f11c000001")
        second = repo.get_record(HARBOR, "fact_c0f11c000002")
        assert second.id in first.conflicts_with
        assert first.id in second.conflicts_with
        hits = repo.search(HARBOR, "sqlite cosine")
        assert any(item.id == "decision_a11ce0000001" for item in hits)
        decoy_hits = repo.search(HARBOR, "Redis")
        assert all(item.id != "fact_deca00000001" for item in decoy_hits)
        decoy = repo.get_record(DECOY, "fact_deca00000001")
        assert "Redis" in decoy.statement
        docs = repo.index.list_documents(HARBOR)
        assert len(docs) == 10
        assert all(row["status"] == "pending" for row in docs)
        original = tmp_path / "documents" / HARBOR / "doc_aa0000000001" / "original.md"
        assert "MARKER_HW_RAM" in original.read_text(encoding="utf-8")
        turns = repo.conversations.load(HARBOR, "conv_aa0000000001").turns
        assert any("Ollama on the host" in turn.content for turn in turns)
        assert any("pizza" in turn.content.lower() for turn in turns if turn.role == "user")
        stored = repo.list_records(HARBOR)
        assert not any("pizza" in searchable_text(item).lower() for item in stored)
        q22 = next(item for item in result.questions if item.id == "q22")
        assert q22.gold_memory_ids == ["decision_a11ce0000001"]
        q24 = next(item for item in result.questions if item.id == "q24")
        assert q24.gold_conversation_ids == ["conv_aa0000000001"]
        assert q24.gold_memory_ids == []
    finally:
        repo.close()
