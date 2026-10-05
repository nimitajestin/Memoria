from pathlib import Path

from core.memory.content import sha256_bytes
from core.schemas.documents import DocumentMeta
from core.storage.documents import DocumentRepository, new_document_id
from core.storage.vault import atomic_write
from evaluation.datasets.controlled.load import HARBOR, load_catalog, load_harbor
from ingestion.indexing.pipeline import index_document, index_project


def test_harbor_markers_survive_indexing(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    first = index_project(tmp_path, HARBOR)
    assert first.failed == 0
    assert first.reindexed == 10
    catalog = load_catalog()
    store = DocumentRepository(tmp_path)
    try:
        chunks = store.list_chunks(HARBOR)
        blob = "\n".join(row["text"] for row in chunks)
        for item in catalog["documents"]:
            for marker in item["markers"].values():
                assert marker in blob
                assert any(marker in row["text"] for row in chunks)
        second = index_project(tmp_path, HARBOR)
        assert second.unchanged == 10
        assert second.reindexed == 0
        original = store.original_path(HARBOR, "doc_aa0000000001")
        original.write_bytes(original.read_bytes() + b"\nMARKER_HW_RAM extra line\n")
        third = index_project(tmp_path, HARBOR)
        assert third.reindexed == 1
        assert third.unchanged == 9
    finally:
        store.close()


def test_empty_and_unsupported_documents(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    store = DocumentRepository(tmp_path)
    try:
        empty_id = new_document_id()
        directory = tmp_path / "documents" / HARBOR / empty_id
        atomic_write(directory / "original.txt", b"")
        store.add(
            DocumentMeta(
                id=empty_id,
                project_id=HARBOR,
                filename="empty.txt",
                file_type="text",
                byte_size=0,
                content_hash=sha256_bytes(b""),
                indexed_at=None,
                status="pending",
                error=None,
                chunk_count=0,
                vault_relpath=f"documents/{HARBOR}/{empty_id}",
            )
        )
        report = index_document(tmp_path, HARBOR, empty_id, documents=store)
        assert report.empty == 1
        assert store.get(HARBOR, empty_id).status == "empty"

        bad_id = new_document_id()
        atomic_write(tmp_path / "documents" / HARBOR / bad_id / "original.bin", b"\x00\x01")
        store.add(
            DocumentMeta(
                id=bad_id,
                project_id=HARBOR,
                filename="notes.bin",
                file_type="text",
                byte_size=2,
                content_hash=sha256_bytes(b"\x00\x01"),
                indexed_at=None,
                status="pending",
                error=None,
                chunk_count=0,
                vault_relpath=f"documents/{HARBOR}/{bad_id}",
            )
        )
        failed = index_document(tmp_path, HARBOR, bad_id, documents=store)
        assert failed.unsupported == 1
        assert store.get(HARBOR, bad_id).status == "unsupported"
    finally:
        store.close()
