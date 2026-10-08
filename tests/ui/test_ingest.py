from pathlib import Path

import pytest

from app.ui.ingest import MAX_UPLOAD_BYTES, ingest_bytes, ingest_inbox, ingest_inbox_path
from core.errors import StorageError
from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from ingestion.indexing.pipeline import index_project


def test_multi_upload_happy_path(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    first = ingest_bytes(tmp_path, HARBOR, "note.md", b"# hello\nMARKER_INGEST")
    second = ingest_bytes(tmp_path, HARBOR, "notes.txt", b"plain text")
    assert first.status == "pending"
    assert second.status == "pending"
    index_project(tmp_path, HARBOR, embedder=HashEmbedder())
    docs = DocumentRepository(tmp_path)
    names = {item.filename for item in docs.list(HARBOR)}
    assert "note.md" in names
    assert "notes.txt" in names
    docs.close()


def test_unsupported_extension(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    with pytest.raises(StorageError) as caught:
        ingest_bytes(tmp_path, HARBOR, "photo.exe", b"MZ")
    assert caught.value.code == "UNSUPPORTED"


def test_oversize_file(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    with pytest.raises(StorageError) as caught:
        ingest_bytes(tmp_path, HARBOR, "huge.md", b"x" * (MAX_UPLOAD_BYTES + 1))
    assert caught.value.code == "VALIDATION"


def test_inbox_import_happy_path(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "from-inbox.md").write_text("# inbox\n", encoding="utf-8")
    added, errors = ingest_inbox(tmp_path, HARBOR, inbox)
    assert errors == []
    assert len(added) == 1
    assert added[0].filename == "from-inbox.md"


def test_inbox_rejects_path_traversal(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(StorageError) as caught:
        ingest_inbox_path(tmp_path, HARBOR, inbox / ".." / "secret.md", inbox)
    assert caught.value.code == "FORBIDDEN"


def test_inbox_rejects_symlink(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    target = tmp_path / "outside.md"
    target.write_text("nope", encoding="utf-8")
    link = inbox / "link.md"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available on this host")
    with pytest.raises(StorageError) as caught:
        ingest_inbox_path(tmp_path, HARBOR, link, inbox)
    assert caught.value.code == "FORBIDDEN"
