import hashlib
import threading
from pathlib import Path

import pytest

from core.errors import StorageError
from core.schemas.conversations import ConversationFile, Turn
from core.schemas.documents import ChunkRecord, DocumentMeta
from core.schemas.memory import utc_now
from core.storage.conversations import ConversationStore
from core.storage.documents import DocumentRepository, new_document_id
from core.storage.memory_repo import MemoryRepository
from core.storage.vault import atomic_write
from tests.conftest import fact_payload


def test_atomic_write_replaces_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "note.yaml"
    atomic_write(path, b"one\n")
    atomic_write(path, b"two\n")
    assert path.read_bytes() == b"two\n"
    assert list(tmp_path.glob(".note.yaml.*.tmp")) == []


def test_project_and_fact_round_trip(repo) -> None:
    project = repo.create_project("project_harbor", "Harbor", "Controlled project.")
    assert project.id == "project_harbor"
    record = repo.create_record("project_harbor", fact_payload())
    loaded = repo.get_record("project_harbor", record.id)
    assert loaded.statement == record.statement
    assert loaded.revision == 1
    status = (repo.root / "memory" / "projects" / "project_harbor" / "status.md").read_text(encoding="utf-8")
    assert "status_project_harbor" in status
    assert repo.list_projects()[0].name == "Harbor"


def test_duplicate_fact_does_not_write_a_second_file(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    repo.create_record("project_harbor", fact_payload())
    with pytest.raises(StorageError) as caught:
        repo.create_record(
            "project_harbor",
            fact_payload(topic="other", statement="the   machine has 8 gb of ram."),
        )
    assert caught.value.code == "CONFLICT"
    assert caught.value.details["reason"] == "duplicate"
    folder = repo.root / "memory" / "projects" / "project_harbor" / "facts"
    assert len(list(folder.glob("*.yaml"))) == 1


def test_fact_conflict_links_and_leaves_the_original_file(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    first = repo.create_record("project_harbor", fact_payload(statement="The machine has 16 GB of RAM."))
    before = (repo.root / "memory" / "projects" / "project_harbor" / "facts" / f"{first.id}.yaml").read_bytes()
    second = repo.create_record("project_harbor", fact_payload())
    assert first.id in second.conflicts_with
    after = (repo.root / "memory" / "projects" / "project_harbor" / "facts" / f"{first.id}.yaml").read_bytes()
    assert after == before


def test_decision_text_update_is_refused_and_revision_mismatch_writes_nothing(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    decision = repo.create_record(
        "project_harbor",
        {
            "type": "decision",
            "topic": "vector_storage",
            "decision": "Use exact cosine search over float32 vectors stored in SQLite.",
            "reason": "The corpus is small and the machine has no spare RAM.",
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    path = repo.root / "memory" / "projects" / "project_harbor" / "decisions" / f"{decision.id}.yaml"
    before = path.read_bytes()
    with pytest.raises(StorageError) as caught:
        repo.update_record(
            "project_harbor",
            decision.id,
            {"decision": "Use a vector database server."},
            decision.revision,
        )
    assert caught.value.code == "VALIDATION"
    assert path.read_bytes() == before
    with pytest.raises(StorageError) as caught:
        repo.update_record(
            "project_harbor",
            decision.id,
            {"confidence": 0.4},
            expected_revision=99,
        )
    assert caught.value.code == "CONFLICT"
    assert path.read_bytes() == before
    view = (repo.root / "memory" / "projects" / "project_harbor" / "decisions.md").read_text(encoding="utf-8")
    assert decision.id in view


def test_decision_supersede_keeps_the_previous_body(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    original = repo.create_record(
        "project_harbor",
        {
            "type": "decision",
            "topic": "vector_storage",
            "decision": "Use exact cosine search.",
            "reason": "RAM is limited.",
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    revised = repo.create_record(
        "project_harbor",
        {
            "type": "decision",
            "topic": "vector_storage",
            "decision": "Use exact cosine search in SQLite.",
            "reason": "Measured latency is acceptable.",
            "supersedes": original.id,
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    stored = repo.get_record("project_harbor", original.id)
    assert stored.status == "superseded"
    assert stored.decision == "Use exact cosine search."
    assert stored.reason == "RAM is limited."
    assert revised.supersedes == original.id
    assert revised.status == "active"


def test_delete_removes_a_fact_and_withdraws_a_decision(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    fact = repo.create_record("project_harbor", fact_payload())
    decision = repo.create_record(
        "project_harbor",
        {
            "type": "decision",
            "topic": "layout",
            "decision": "Keep YAML as the source of truth.",
            "reason": "People can edit it.",
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    assert repo.delete_record("project_harbor", fact.id, fact.revision) is None
    with pytest.raises(StorageError) as caught:
        repo.get_record("project_harbor", fact.id)
    assert caught.value.code == "NOT_FOUND"
    withdrawn = repo.delete_record("project_harbor", decision.id, decision.revision)
    assert withdrawn.status == "withdrawn"
    assert repo.get_record("project_harbor", decision.id).status == "withdrawn"


def test_malformed_yaml_is_not_rewritten(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    fact = repo.create_record("project_harbor", fact_payload())
    path = repo.root / "memory" / "projects" / "project_harbor" / "facts" / f"{fact.id}.yaml"
    before_hash = repo.index_entry("project_harbor", fact.id)["content_hash"]
    path.write_text("[\n", encoding="utf-8")
    with pytest.raises(StorageError) as caught:
        repo.get_record("project_harbor", fact.id)
    assert caught.value.code == "MALFORMED"
    assert path.read_text(encoding="utf-8") == "[\n"
    assert repo.index_entry("project_harbor", fact.id)["content_hash"] == before_hash


def test_external_edit_is_indexed_on_read(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    fact = repo.create_record("project_harbor", fact_payload())
    path = repo.root / "memory" / "projects" / "project_harbor" / "facts" / f"{fact.id}.yaml"
    path.write_bytes(path.read_bytes().replace(b"8 GB", b"16 GB"))
    loaded = repo.get_record("project_harbor", fact.id)
    assert "16 GB" in loaded.statement
    assert repo.index_entry("project_harbor", fact.id)["content_hash"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_quote_must_be_in_the_cited_chunk(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    docs = DocumentRepository(repo.root, repo.index)
    document_id = new_document_id()
    docs.add(
        DocumentMeta(
            id=document_id,
            project_id="project_harbor",
            filename="notes.md",
            file_type="markdown",
            byte_size=32,
            content_hash="a" * 64,
            indexed_at=utc_now(),
            status="indexed",
            error=None,
            chunk_count=1,
            vault_relpath=f"documents/project_harbor/{document_id}",
        )
    )
    text = "The retrieval index uses SQLite."
    chunk_id = "chunk_0123456789ab"
    docs.replace_chunks(
        "project_harbor",
        document_id,
        [
            ChunkRecord(
                id=chunk_id,
                document_id=document_id,
                project_id="project_harbor",
                chunk_index=0,
                section="Retrieval",
                page=None,
                line_start=1,
                line_end=1,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                char_count=len(text),
                text=text,
                created_at=utc_now(),
            )
        ]
    )
    created = repo.create_record(
        "project_harbor",
        fact_payload(
            source={"kind": "document", "ref": chunk_id, "quote": "uses SQLite"},
        ),
    )
    assert created.source.quote == "uses SQLite"
    with pytest.raises(StorageError) as caught:
        repo.create_record(
            "project_harbor",
            fact_payload(
                topic="other",
                statement="A different fact about the index.",
                source={"kind": "document", "ref": chunk_id, "quote": "Qdrant"},
            ),
        )
    assert caught.value.code == "VALIDATION"


def test_capacity_and_project_boundary(repo) -> None:
    bounded = type(repo)(repo.root, index=repo.index, caps={"fact": 1})
    bounded.create_project("project_harbor", "Harbor")
    bounded.create_record("project_harbor", fact_payload())
    with pytest.raises(StorageError) as caught:
        bounded.create_record(
            "project_harbor",
            fact_payload(topic="notes", statement="A second fact that is different."),
        )
    assert caught.value.details["reason"] == "capacity"
    bounded.create_project("project_other", "Other")
    with pytest.raises(StorageError) as caught:
        bounded.get_record("project_other", bounded.list_records("project_harbor")[0].id)
    assert caught.value.code == "NOT_FOUND"


def test_status_and_goal_updates_require_the_current_revision(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    status = repo.get_record("project_harbor", "status_project_harbor")
    updated = repo.update_record(
        "project_harbor",
        status.id,
        {"phase": "storage", "summary": "Phase 1 storage is in place."},
        status.revision,
    )
    assert updated.revision == status.revision + 1
    view = (repo.root / "memory" / "projects" / "project_harbor" / "status.md").read_text(encoding="utf-8")
    assert "Phase 1 storage is in place." in view
    with pytest.raises(StorageError) as caught:
        repo.update_record("project_harbor", status.id, {"phase": "later"}, status.revision)
    assert caught.value.code == "CONFLICT"
    goal = repo.create_record(
        "project_harbor",
        {
            "type": "goal",
            "statement": "Finish the storage layer.",
            "goal_status": "open",
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    done = repo.update_record("project_harbor", goal.id, {"goal_status": "done"}, goal.revision)
    assert done.goal_status == "done"
    assert done.statement == "Finish the storage layer."


def test_concurrent_update_allows_one_writer(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    record = repo.create_record("project_harbor", fact_payload())
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker(statement: str) -> None:
        barrier.wait()
        try:
            repo.update_record("project_harbor", record.id, {"statement": statement}, 1)
            results.append("ok")
        except StorageError as exc:
            results.append(exc.code)

    threads = [
        threading.Thread(target=worker, args=("Alpha statement for the concurrent update.",)),
        threading.Thread(target=worker, args=("Beta statement for the concurrent update.",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["CONFLICT", "ok"]
    assert repo.get_record("project_harbor", record.id).revision == 2


def test_search_and_log_omit_the_full_body_from_the_log(repo) -> None:
    repo.create_project("project_harbor", "Harbor")
    repo.create_record("project_harbor", fact_payload(statement="SQLite stores the chunk vectors."))
    repo.create_record(
        "project_harbor",
        fact_payload(topic="unrelated", statement="The UI has four views."),
    )
    hits = repo.search("project_harbor", "sqlite vectors")
    assert len(hits) == 1
    assert "SQLite" in hits[0].snippet
    log = (repo.root / "logs" / "memoria.jsonl").read_text(encoding="utf-8")
    assert "memory_create" in log
    assert "SQLite stores the chunk vectors." not in log


def test_conversation_round_trip(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    conversation = ConversationFile(
        id="conv_0123456789ab",
        project_id="project_harbor",
        source="import",
        origin_format="markdown",
        created_at=utc_now(),
        title="Planning chat",
        turns=[Turn(role="user", content="We should keep Ollama on the host.", timestamp=None)],
    )
    store.save(conversation)
    loaded = store.load("project_harbor", conversation.id)
    assert loaded.turns[0].content.startswith("We should keep Ollama")


def test_symlink_inside_the_vault_is_refused(repo, tmp_path: Path) -> None:
    repo.create_project("project_harbor", "Harbor")
    outside = tmp_path / "outside"
    outside.mkdir()
    facts = repo.root / "memory" / "projects" / "project_harbor" / "facts"
    try:
        facts.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating a directory symlink requires extra Windows privilege")
    with pytest.raises(StorageError) as caught:
        repo.create_record("project_harbor", fact_payload())
    assert caught.value.code == "FORBIDDEN"


def test_creating_twenty_facts_stays_within_a_small_allocation(tmp_path: Path) -> None:
    import tracemalloc

    tracemalloc.start()
    store = MemoryRepository(tmp_path)
    store.create_project("project_harbor", "Harbor")
    for index in range(20):
        store.create_record(
            "project_harbor",
            fact_payload(topic=f"topic-{index}", statement=f"Fact number {index} stays on disk."),
        )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    store.close()
    assert peak < 32 * 1024 * 1024
