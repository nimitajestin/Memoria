"""Rebuild SQLite from vault files after the index is missing or unreadable."""

from __future__ import annotations

from pathlib import Path

from core.safety import check_project_id
from core.schemas.documents import DocumentMeta
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from core.storage.vault import read_yaml
from ingestion.embedding.batch import Embedder
from ingestion.indexing.pipeline import IndexReport, index_document


def rebuild_index(data_root: Path, embedder: Embedder | None = None) -> IndexReport:
    root = Path(data_root).resolve()
    memory = MemoryRepository(root)
    documents = DocumentRepository(root, memory.index)
    combined = IndexReport()
    try:
        docs_root = root / "documents"
        if docs_root.exists():
            for project_dir in sorted(path for path in docs_root.iterdir() if path.is_dir()):
                try:
                    project_id = check_project_id(project_dir.name)
                except Exception:
                    continue
                for doc_dir in sorted(path for path in project_dir.iterdir() if path.is_dir()):
                    meta_path = doc_dir / "meta.yaml"
                    if not meta_path.exists():
                        continue
                    meta = DocumentMeta.model_validate(read_yaml(meta_path))
                    documents.add(meta)
                    report = index_document(
                        root,
                        project_id,
                        meta.id,
                        force=True,
                        documents=documents,
                        embedder=embedder,
                    )
                    combined.unchanged += report.unchanged
                    combined.reindexed += report.reindexed
                    combined.empty += report.empty
                    combined.failed += report.failed
                    combined.unsupported += report.unsupported
                    combined.truncated += report.truncated
                    combined.errors.extend(report.errors)
        for project in memory.list_projects():
            memory.list_records(project.id)
    finally:
        documents.close()
        memory.close()
    return combined
