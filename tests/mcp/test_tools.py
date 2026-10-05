from pathlib import Path

from core.errors import StorageError
from core.retrieval.hash_embedder import HashEmbedder
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from mcp_server.server import build_server
from tests.mcp.conftest import call_tool, load_indexed_harbor


def test_each_tool_accepts_a_valid_call_and_rejects_bad_input(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    valid = {
        "memory.search": {"project_id": HARBOR, "query": "SQLite"},
        "memory.get": {"project_id": HARBOR, "id": "decision_a11ce0000001"},
        "documents.list": {"project_id": HARBOR},
        "documents.get": {"project_id": HARBOR, "document_id": "doc_aa0000000001"},
        "documents.search": {"project_id": HARBOR, "query": "Harbor RAM"},
        "project.get_status": {"project_id": HARBOR},
    }
    for name, arguments in valid.items():
        payload = call_tool(server, name, arguments)
        assert payload["ok"] is True, name
        unknown = call_tool(server, name, {**arguments, "project_id": "missing_project"})
        assert unknown["ok"] is False
        assert unknown["error"]["code"] in {"NOT_FOUND", "FORBIDDEN", "VALIDATION"}
    empty = call_tool(server, "memory.search", {"project_id": HARBOR, "query": ""})
    assert empty["ok"] is False
    assert empty["error"]["code"] == "VALIDATION"


def test_memory_create_get_duplicate_and_decision_rules(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    created = call_tool(
        server,
        "memory.create",
        {
            "project_id": HARBOR,
            "record": {
                "type": "fact",
                "topic": "notes",
                "statement": "Harbor tests the MCP adapter.",
                "source": {"kind": "user", "ref": None, "quote": None},
            },
        },
    )
    assert created["ok"] is True
    record_id = created["data"]["id"]
    fetched = call_tool(server, "memory.get", {"project_id": HARBOR, "id": record_id})
    assert fetched["data"]["statement"].startswith("Harbor tests")
    missing = call_tool(server, "memory.get", {"project_id": HARBOR, "id": "fact_ffffffffffff"})
    assert missing["error"]["code"] == "NOT_FOUND"
    duplicate = call_tool(
        server,
        "memory.create",
        {
            "project_id": HARBOR,
            "record": {
                "type": "fact",
                "topic": "other",
                "statement": "Harbor tests the MCP adapter.",
                "source": {"kind": "user", "ref": None, "quote": None},
            },
        },
    )
    assert duplicate["error"]["code"] == "CONFLICT"
    facts = list((tmp_path / "memory" / "projects" / HARBOR / "facts").glob("*.yaml"))
    assert len(facts) == 4
    path = tmp_path / "memory" / "projects" / HARBOR / "decisions" / "decision_a11ce0000001.yaml"
    before = path.read_bytes()
    updated = call_tool(
        server,
        "memory.update",
        {
            "project_id": HARBOR,
            "id": "decision_a11ce0000001",
            "patch": {"decision": "Use a vector database."},
            "expected_revision": 1,
        },
    )
    assert updated["error"]["code"] == "VALIDATION"
    assert path.read_bytes() == before
    mismatch = call_tool(
        server,
        "memory.update",
        {
            "project_id": HARBOR,
            "id": "fact_8ba000000001",
            "patch": {"statement": "The Harbor workstation has 8 GB of RAM still."},
            "expected_revision": 99,
        },
    )
    assert mismatch["error"]["code"] == "CONFLICT"


def test_malformed_memory_is_not_rewritten(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    path = tmp_path / "memory" / "projects" / HARBOR / "facts" / "fact_8ba000000001.yaml"
    path.write_text("[\n", encoding="utf-8")
    payload = call_tool(server, "memory.get", {"project_id": HARBOR, "id": "fact_8ba000000001"})
    assert payload["ok"] is False
    assert payload["error"]["code"] in {"MALFORMED", "INTERNAL"}
    assert path.read_text(encoding="utf-8") == "[\n"


def test_path_escape_and_bad_document_id(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    escaped = call_tool(server, "memory.search", {"project_id": "../other", "query": "x"})
    assert escaped["error"]["code"] == "FORBIDDEN"
    bad = call_tool(
        server,
        "documents.get",
        {"project_id": HARBOR, "document_id": "../secret"},
    )
    assert bad["error"]["code"] == "VALIDATION"
    missing = call_tool(
        server,
        "documents.get",
        {"project_id": HARBOR, "document_id": "doc_ffffffffffff"},
    )
    assert missing["error"]["code"] == "NOT_FOUND"


def test_document_search_and_reindex(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    first = call_tool(server, "documents.search", {"project_id": HARBOR, "query": "SQLite cosine"})
    assert first["ok"] is True
    ids = [item["chunk_id"] for item in first["data"]["hits"]]
    second = call_tool(server, "documents.search", {"project_id": HARBOR, "query": "SQLite cosine"})
    assert [item["chunk_id"] for item in second["data"]["hits"]] == ids
    listed = call_tool(server, "documents.list", {"project_id": HARBOR})
    assert listed["ok"] is True
    reindexed = call_tool(server, "documents.reindex", {"project_id": HARBOR})
    assert reindexed["ok"] is True
    assert reindexed["data"]["unchanged"] >= 10


def test_status_update_and_delete(tmp_path: Path) -> None:
    server, _embedder = load_indexed_harbor(tmp_path)
    status = call_tool(server, "project.get_status", {"project_id": HARBOR})
    revision = status["data"]["record"]["revision"]
    updated = call_tool(
        server,
        "project.update_status",
        {
            "project_id": HARBOR,
            "summary": "MCP adapter is live.",
            "phase": "mcp",
            "expected_revision": revision,
            "blockers": [],
        },
    )
    assert updated["ok"] is True
    fact = call_tool(
        server,
        "memory.create",
        {
            "project_id": HARBOR,
            "record": {
                "type": "fact",
                "topic": "tmp",
                "statement": "A disposable Harbor fact.",
                "source": {"kind": "user", "ref": None, "quote": None},
            },
        },
    )
    deleted = call_tool(
        server,
        "memory.delete",
        {
            "project_id": HARBOR,
            "id": fact["data"]["id"],
            "expected_revision": fact["data"]["revision"],
        },
    )
    assert deleted["ok"] is True


def test_reindex_embedding_failure_leaves_other_documents(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    index_project = __import__("ingestion.indexing.pipeline", fromlist=["index_project"]).index_project
    good = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=good)

    class Boom:
        model = "boom"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise StorageError("FAILED_DEPENDENCY", "Embedding model is unavailable.")

    server = build_server(tmp_path, Boom())
    payload = call_tool(
        server,
        "documents.reindex",
        {"project_id": HARBOR, "document_id": "doc_aa0000000002", "force": True},
    )
    assert payload["ok"] is True
    assert payload["data"]["failed"] == 1
    listed = call_tool(server, "documents.list", {"project_id": HARBOR})
    by_id = {item["id"]: item for item in listed["data"]["documents"]}
    assert by_id["doc_aa0000000002"]["status"] == "failed"
    assert by_id["doc_aa0000000001"]["status"] == "indexed"
