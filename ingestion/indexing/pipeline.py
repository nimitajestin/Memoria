"""Incremental parse, chunk, and persist. Embeddings are Phase 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from core.errors import StorageError
from core.logging import log_event
from core.memory.content import sha256_bytes
from core.safety import FileLock, check_project_id
from core.schemas.documents import ChunkRecord, DocumentMeta
from core.schemas.memory import utc_now
from core.storage.documents import DocumentRepository, new_chunk_id
from ingestion.chunking.chunk import CAP, chunk_units
from ingestion.embedding.batch import Embedder, embed_chunks
from ingestion.parsers.detect import detect_type
from ingestion.parsers.dispatch import parse_bytes


@dataclass
class IndexReport:
    unchanged: int = 0
    reindexed: int = 0
    empty: int = 0
    failed: int = 0
    unsupported: int = 0
    truncated: int = 0
    duration_ms: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def index_project(
    data_root: Path,
    project_id: str,
    *,
    force: bool = False,
    documents: DocumentRepository | None = None,
    embedder: Embedder | None = None,
) -> IndexReport:
    project_id = check_project_id(project_id)
    started = perf_counter()
    owned = documents is None
    store = documents or DocumentRepository(data_root)
    report = IndexReport()
    try:
        lock = FileLock(Path(data_root).resolve() / "documents" / project_id / ".lock")
        with lock:
            for meta in store.list(project_id):
                _index_one(store, meta, force=force, report=report, embedder=embedder)
                del meta
    finally:
        if owned:
            store.close()
    report.duration_ms = int((perf_counter() - started) * 1000)
    log_event(
        Path(data_root),
        "index_project",
        project_id=project_id,
        count=report.reindexed,
        latency_ms=report.duration_ms,
    )
    return report


def index_document(
    data_root: Path,
    project_id: str,
    document_id: str,
    *,
    force: bool = False,
    documents: DocumentRepository | None = None,
    embedder: Embedder | None = None,
) -> IndexReport:
    project_id = check_project_id(project_id)
    started = perf_counter()
    owned = documents is None
    store = documents or DocumentRepository(data_root)
    report = IndexReport()
    try:
        meta = store.get(project_id, document_id)
        lock = FileLock(Path(data_root).resolve() / "documents" / project_id / ".lock")
        with lock:
            _index_one(store, meta, force=force, report=report, embedder=embedder)
    finally:
        if owned:
            store.close()
    report.duration_ms = int((perf_counter() - started) * 1000)
    return report


def _index_one(
    store: DocumentRepository,
    meta: DocumentMeta,
    *,
    force: bool,
    report: IndexReport,
    embedder: Embedder | None,
) -> None:
    try:
        path = store.original_path(meta.project_id, meta.id)
        data = path.read_bytes()
        digest = sha256_bytes(data)
        complete = embedder is None or store.embeddings_complete(meta.id)
        if (
            not force
            and digest == meta.content_hash
            and meta.status in {"indexed", "empty", "truncated"}
            and complete
        ):
            report.unchanged += 1
            return
        kind = detect_type(path)
        units = parse_bytes(path, data)[1]
        drafts = chunk_units(units)
        del units
        status = "indexed"
        if not drafts:
            status = "empty"
            report.empty += 1
        elif len(drafts) > CAP:
            drafts = drafts[:CAP]
            status = "truncated"
            report.truncated += 1
        else:
            report.reindexed += 1
        now = utc_now()
        chunks = [
            ChunkRecord(
                id=new_chunk_id(),
                document_id=meta.id,
                project_id=meta.project_id,
                chunk_index=index,
                section=draft.section,
                page=draft.page,
                line_start=draft.line_start,
                line_end=draft.line_end,
                content_hash=sha256_bytes(draft.text.encode("utf-8")),
                char_count=len(draft.text),
                text=draft.text,
                created_at=now,
            )
            for index, draft in enumerate(drafts)
        ]
        store.replace_chunks(meta.project_id, meta.id, chunks)
        if embedder is not None and chunks:
            embed_chunks(store, meta.project_id, chunks, embedder)
        updated = DocumentMeta(
            id=meta.id,
            project_id=meta.project_id,
            filename=meta.filename,
            file_type=kind,
            byte_size=len(data),
            content_hash=digest,
            indexed_at=now,
            status=status,
            error=None,
            chunk_count=len(chunks),
            vault_relpath=meta.vault_relpath,
        )
        store.save_meta(updated)
        log_event(
            store.root,
            "index_document",
            project_id=meta.project_id,
            document_id=meta.id,
            count=len(chunks),
        )
    except StorageError as exc:
        _mark_failed(store, meta, report, exc.code, str(exc))
    except Exception as exc:
        _mark_failed(store, meta, report, "INTERNAL", str(exc))


def _mark_failed(
    store: DocumentRepository,
    meta: DocumentMeta,
    report: IndexReport,
    code: str,
    message: str,
) -> None:
    status = "unsupported" if code == "UNSUPPORTED" else "failed"
    if status == "unsupported":
        report.unsupported += 1
    else:
        report.failed += 1
    report.errors.append({"document_id": meta.id, "code": code, "message": message})
    try:
        store.replace_chunks(meta.project_id, meta.id, [])
        store.save_meta(
            DocumentMeta(
                id=meta.id,
                project_id=meta.project_id,
                filename=meta.filename,
                file_type=meta.file_type,
                byte_size=meta.byte_size,
                content_hash=meta.content_hash,
                indexed_at=utc_now(),
                status=status,
                error=message[:500],
                chunk_count=0,
                vault_relpath=meta.vault_relpath,
            )
        )
    except StorageError:
        pass
    log_event(
        store.root,
        "index_failed",
        project_id=meta.project_id,
        document_id=meta.id,
        error_code=code,
    )
