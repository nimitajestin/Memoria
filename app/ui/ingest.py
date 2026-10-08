"""Copy uploaded files into the vault, then reuse the existing index pipeline."""

from __future__ import annotations

from pathlib import Path

from core.errors import StorageError
from core.memory.content import sha256_bytes
from core.safety import check_project_id, resolve_inside, safe_filename
from core.schemas.documents import DocumentMeta
from core.storage.documents import DocumentRepository, new_document_id
from core.storage.memory_repo import MemoryRepository
from ingestion.indexing.pipeline import IndexReport, index_project
from ingestion.parsers.detect import detect_type

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
INBOX_PATH = Path("/vault/inbox")


def ingest_bytes(data_root: Path, project_id: str, filename: str, data: bytes) -> DocumentMeta:
    root = Path(data_root).resolve()
    project_id = check_project_id(project_id)
    name = safe_filename(filename)
    if len(data) > MAX_UPLOAD_BYTES:
        raise StorageError("VALIDATION", "Upload exceeds 20 MB.")
    kind = detect_type(Path(name))
    document_id = new_document_id()
    directory = root / "documents" / project_id / document_id
    dest = resolve_inside(root, directory / f"original{Path(name).suffix}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    meta = DocumentMeta(
        id=document_id,
        project_id=project_id,
        filename=name,
        file_type=kind,
        byte_size=len(data),
        content_hash=sha256_bytes(data),
        indexed_at=None,
        status="pending",
        error=None,
        chunk_count=0,
        vault_relpath=f"documents/{project_id}/{document_id}",
    )
    memory = MemoryRepository(root)
    documents = DocumentRepository(root, memory.index)
    try:
        documents.add(meta)
    finally:
        documents.close()
        memory.close()
    return meta


def reindex_project(data_root: Path, project_id: str) -> IndexReport:
    from core.ollama import OllamaEmbedder
    from core.retrieval.hash_embedder import HashEmbedder

    try:
        embedder = OllamaEmbedder()
        return index_project(data_root, project_id, embedder=embedder)
    except Exception:
        return index_project(data_root, project_id, embedder=HashEmbedder())
