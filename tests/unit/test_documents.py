import struct
from pathlib import Path

import pytest

from core.errors import StorageError
from core.schemas.documents import ChunkRecord, DocumentMeta
from core.schemas.memory import utc_now
from core.storage.db import IndexDatabase
from core.storage.documents import DocumentRepository, new_document_id, pack_vector


def _meta(project_id: str = "project_harbor") -> DocumentMeta:
    document_id = new_document_id()
    return DocumentMeta(
        id=document_id,
        project_id=project_id,
        filename="notes.md",
        file_type="markdown",
        byte_size=4,
        content_hash="ab" * 32,
        indexed_at=utc_now(),
        status="indexed",
        error=None,
        chunk_count=0,
        vault_relpath=f"documents/{project_id}/{document_id}",
    )


def _chunk(document_id: str, text: str = "hello") -> ChunkRecord:
    return ChunkRecord(
        id="chunk_0123456789ab",
        document_id=document_id,
        project_id="project_harbor",
        chunk_index=0,
        section=None,
        page=None,
        line_start=1,
        line_end=1,
        content_hash="cd" * 32,
        char_count=len(text),
        text=text,
        created_at=utc_now(),
    )


def test_embedding_dimension_is_sticky_until_rebuild(tmp_path: Path) -> None:
    docs = DocumentRepository(tmp_path)
    meta = _meta()
    docs.add(meta)
    docs.replace_chunks("project_harbor", meta.id, [_chunk(meta.id)])
    docs.put_embedding("project_harbor", "chunk_0123456789ab", "nomic-embed-text", [0.1, 0.2])
    with pytest.raises(StorageError) as caught:
        docs.put_embedding("project_harbor", "chunk_0123456789ab", "nomic-embed-text", [0.1, 0.2, 0.3])
    assert caught.value.code == "VALIDATION"
    docs.clear_embeddings()
    docs.put_embedding("project_harbor", "chunk_0123456789ab", "all-minilm", [0.1, 0.2, 0.3])
    assert docs.embedding_count() == 1
    docs.delete("project_harbor", meta.id)
    assert docs.embedding_count() == 0
    with pytest.raises(StorageError):
        docs.get("project_harbor", meta.id)
    docs.close()


def test_database_reopens_with_the_same_rows(tmp_path: Path) -> None:
    path = tmp_path / "index" / "memoria.sqlite"
    database = IndexDatabase(path)
    docs = DocumentRepository(tmp_path, database)
    meta = _meta()
    docs.add(meta)
    database.close()
    reopened = IndexDatabase(path)
    row = reopened.get_document("project_harbor", meta.id)
    assert row is not None
    assert row["filename"] == "notes.md"
    version = reopened.schema_version()
    assert version == "1"
    reopened.close()


def test_pack_vector_is_little_endian_float32() -> None:
    packed = pack_vector([1.0])
    assert packed == struct.pack("<1f", 1.0)
