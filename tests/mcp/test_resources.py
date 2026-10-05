from pathlib import Path

from evaluation.datasets.controlled.load import HARBOR
from tests.mcp.conftest import load_indexed_harbor, read_resource


def test_resources_return_seeded_knowledge(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    status = read_resource(server, f"project://{HARBOR}/status")
    assert "status_project_harbor" in status
    decisions = read_resource(server, f"project://{HARBOR}/decisions")
    assert "decision_a11ce0000001" in decisions
    knowledge = read_resource(server, f"project://{HARBOR}/knowledge")
    assert "knowledge_aa0000000001" in knowledge or "blue" in knowledge.lower()
    catalog = read_resource(server, f"project://{HARBOR}/memory")
    assert "decision_a11ce0000001" in catalog
    document = read_resource(server, "document://doc_aa0000000001")
    assert "hardware.md" in document
    conversation = read_resource(server, "conversation://conv_aa0000000001")
    assert "Ollama" in conversation


def test_missing_resource_does_not_stacktrace(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    try:
        read_resource(server, "document://doc_ffffffffffff")
    except Exception as exc:
        text = str(exc).lower()
        assert "traceback" not in text
        assert "not found" in text or "error" in text
