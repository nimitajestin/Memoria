"""Document metadata in SQLite and meta.yaml. Parsing files is a later phase."""

from __future__ import annotations

import struct
import uuid
from pathlib import Path

from core.errors import StorageError
from core.safety import check_project_id, resolve_inside, safe_filename
from core.schemas.documents import ChunkRecord, DocumentMeta
from core.schemas.memory import utc_now
from core.storage.db import IndexDatabase
from core.storage.vault import atomic_write, canonical_bytes, read_yaml, restore_files


def pack_vector(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *[float(value) for value in values])


class DocumentRepository:
    def __init__(self, data_root: Path, index: IndexDatabase | None = None) -> None:
        self.root = Path(data_root).resolve()
        self.index = index or IndexDatabase(self.root / "index" / "memoria.sqlite")
        self._owns_index = index is None

    def close(self) -> None:
        if self._owns_index:
            self.index.close()

    def add(self, meta: DocumentMeta) -> DocumentMeta:
        check_project_id(meta.project_id)
        safe_filename(meta.filename)
        directory = self.root / "documents" / meta.project_id / meta.id
        path = resolve_inside(self.root, directory / "meta.yaml")
        expected = f"documents/{meta.project_id}/{meta.id}"
        if meta.vault_relpath != expected:
            raise StorageError("VALIDATION", "Document vault path does not match its id.")
        data = canonical_bytes(meta)
        previous = None
        try:
            if path.exists():
                previous = [(path, path.read_bytes())]
            atomic_write(path, data)
            self.index.upsert_document(meta.model_dump(mode="json"))
        except Exception:
            if previous is not None:
                restore_files(previous)
            elif path.exists():
                path.unlink()
            raise
        return meta

    def get(self, project_id: str, document_id: str) -> DocumentMeta:
        row = self.index.get_document(check_project_id(project_id), document_id)
        if row is None:
            raise StorageError("NOT_FOUND", "Document is not in this project.")
        return DocumentMeta.model_validate(row)

    def list(self, project_id: str) -> list[DocumentMeta]:
        rows = self.index.list_documents(check_project_id(project_id))
        return [DocumentMeta.model_validate(row) for row in rows]

    def delete(self, project_id: str, document_id: str) -> None:
        project_id = check_project_id(project_id)
        self.index.delete_document(project_id, document_id)
        directory = self.root / "documents" / project_id / document_id
        if directory.exists():
            _remove_tree(self.root, directory)

    def replace_chunks(self, project_id: str, document_id: str, chunks: list[ChunkRecord]) -> None:
        if any(item.document_id != document_id or item.project_id != project_id for item in chunks):
            raise StorageError("VALIDATION", "Chunks must belong to one document.")
        rows = [item.model_dump(mode="json") for item in chunks]
        self.index.replace_chunks(check_project_id(project_id), document_id, rows)

    def list_chunks(self, project_id: str, document_id: str | None = None) -> list[dict]:
        return self.index.list_chunks(check_project_id(project_id), document_id)

    def original_path(self, project_id: str, document_id: str) -> Path:
        directory = resolve_inside(
            self.root,
            self.root / "documents" / check_project_id(project_id) / document_id,
        )
        matches = [
            path
            for path in directory.glob("original.*")
            if path.is_file() and not path.is_symlink()
        ]
        if len(matches) != 1:
            raise StorageError("NOT_FOUND", "Document original file was not found.")
        return resolve_inside(self.root, matches[0])

    def save_meta(self, meta: DocumentMeta) -> DocumentMeta:
        return self.add(meta)

    def embeddings_complete(self, document_id: str) -> bool:
        return self.index.embeddings_complete(document_id)

    def put_embedding(self, project_id: str, chunk_id: str, model: str, values: list[float]) -> None:
        if not values:
            raise StorageError("VALIDATION", "Embedding vector is empty.")
        self.index.put_embedding(
            check_project_id(project_id),
            chunk_id,
            model,
            len(values),
            pack_vector(values),
            utc_now(),
        )

    def clear_embeddings(self) -> None:
        self.index.clear_embeddings()

    def embedding_count(self) -> int:
        return self.index.embedding_count()


def new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:12]}"


def new_chunk_id() -> str:
    return f"chunk_{uuid.uuid4().hex[:12]}"


def _remove_tree(root: Path, directory: Path) -> None:
    resolved = resolve_inside(root, directory)
    if not resolved.is_dir():
        raise StorageError("VALIDATION", "Document path is not a directory.")
    files = [path for path in resolved.rglob("*") if path.is_file() or path.is_symlink()]
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise StorageError("FORBIDDEN", "Symlinks are not allowed inside the vault.")
        path.unlink()
    dirs = sorted((path for path in resolved.rglob("*") if path.is_dir()), reverse=True)
    for path in dirs:
        path.rmdir()
    resolved.rmdir()


def read_meta(path: Path) -> DocumentMeta:
    return DocumentMeta.model_validate(read_yaml(path))
