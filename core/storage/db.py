"""SQLite metadata, chunk text, and embedding blobs."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from core.errors import StorageError

TABLES = """
CREATE TABLE IF NOT EXISTS index_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  file_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  indexed_at TEXT,
  vault_relpath TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  section TEXT,
  page INTEGER,
  line_start INTEGER,
  line_end INTEGER,
  content_hash TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dimension INTEGER NOT NULL,
  vector BLOB NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_index (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  topic TEXT,
  revision INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  vault_relpath TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_memory_project_type ON memory_index(project_id, type, status);
"""


class IndexDatabase:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(TABLES)
        row = self._conn.execute(
            "SELECT value FROM index_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO index_meta(key, value) VALUES ('schema_version', '1')"
            )
            self._conn.commit()
        elif row["value"] != "1":
            raise StorageError("INTERNAL", "Unsupported index schema version.")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def schema_version(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM index_meta WHERE key = 'schema_version'"
            ).fetchone()
        return str(row["value"])

    def update_memory_rows(self, upserts: list[dict], delete_ids: list[str]) -> None:
        with self._lock:
            try:
                for row in upserts:
                    self._conn.execute(
                        """
                        INSERT INTO memory_index (
                            id, project_id, type, status, topic, revision,
                            content_hash, vault_relpath, updated_at
                        ) VALUES (
                            :id, :project_id, :type, :status, :topic, :revision,
                            :content_hash, :vault_relpath, :updated_at
                        )
                        ON CONFLICT(id) DO UPDATE SET
                            project_id = excluded.project_id,
                            type = excluded.type,
                            status = excluded.status,
                            topic = excluded.topic,
                            revision = excluded.revision,
                            content_hash = excluded.content_hash,
                            vault_relpath = excluded.vault_relpath,
                            updated_at = excluded.updated_at
                        """,
                        row,
                    )
                for record_id in delete_ids:
                    self._conn.execute("DELETE FROM memory_index WHERE id = ?", (record_id,))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def get_memory_row(self, record_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_index WHERE id = ?",
                (record_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_memory_rows(self, project_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory_index WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_document(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO documents (
                    id, project_id, filename, file_type, byte_size, content_hash,
                    status, error, chunk_count, indexed_at, vault_relpath
                ) VALUES (
                    :id, :project_id, :filename, :file_type, :byte_size, :content_hash,
                    :status, :error, :chunk_count, :indexed_at, :vault_relpath
                )
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    filename = excluded.filename,
                    file_type = excluded.file_type,
                    byte_size = excluded.byte_size,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    error = excluded.error,
                    chunk_count = excluded.chunk_count,
                    indexed_at = excluded.indexed_at,
                    vault_relpath = excluded.vault_relpath
                """,
                row,
            )
            self._conn.commit()

    def get_document(self, project_id: str, document_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE id = ? AND project_id = ?",
                (document_id, project_id),
            ).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM documents WHERE project_id = ? ORDER BY filename",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_chunks(self, project_id: str, document_id: str, rows: list[dict]) -> None:
        with self._lock:
            owner = self._conn.execute(
                "SELECT project_id FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if owner is None or owner["project_id"] != project_id:
                raise StorageError("NOT_FOUND", "Document is not in this project.")
            try:
                self._conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
                for row in rows:
                    self._conn.execute(
                        """
                        INSERT INTO chunks (
                            id, document_id, project_id, chunk_index, section, page,
                            line_start, line_end, content_hash, char_count, text, created_at
                        ) VALUES (
                            :id, :document_id, :project_id, :chunk_index, :section, :page,
                            :line_start, :line_end, :content_hash, :char_count, :text, :created_at
                        )
                        """,
                        row,
                    )
                self._conn.execute(
                    "UPDATE documents SET chunk_count = ? WHERE id = ?",
                    (len(rows), document_id),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def list_chunks(self, project_id: str, document_id: str | None = None) -> list[dict]:
        with self._lock:
            if document_id is None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM chunks
                    WHERE project_id = ?
                    ORDER BY document_id, chunk_index
                    """,
                    (project_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM chunks
                    WHERE project_id = ? AND document_id = ?
                    ORDER BY chunk_index
                    """,
                    (project_id, document_id),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_chunk(self, project_id: str, chunk_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chunks WHERE id = ? AND project_id = ?",
                (chunk_id, project_id),
            ).fetchone()
        return dict(row) if row else None

    def list_chunk_texts(self, project_id: str, document_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT text FROM chunks
                WHERE project_id = ? AND document_id = ?
                ORDER BY chunk_index
                """,
                (project_id, document_id),
            ).fetchall()
        return [row["text"] for row in rows]

    def put_embedding(
        self,
        project_id: str,
        chunk_id: str,
        model: str,
        dimension: int,
        vector: bytes,
        created_at: str,
    ) -> None:
        if len(vector) != dimension * 4:
            raise StorageError("VALIDATION", "Vector byte length does not match its dimension.")
        with self._lock:
            chunk = self._conn.execute(
                "SELECT project_id FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            if chunk is None or chunk["project_id"] != project_id:
                raise StorageError("NOT_FOUND", "Chunk is not in this project.")
            current_model = self._conn.execute(
                "SELECT value FROM index_meta WHERE key = 'embedding_model'"
            ).fetchone()
            current_dim = self._conn.execute(
                "SELECT value FROM index_meta WHERE key = 'embedding_dimension'"
            ).fetchone()
            if current_model is None:
                self._conn.execute(
                    "INSERT INTO index_meta(key, value) VALUES ('embedding_model', ?)",
                    (model,),
                )
                self._conn.execute(
                    "INSERT INTO index_meta(key, value) VALUES ('embedding_dimension', ?)",
                    (str(dimension),),
                )
            elif current_model["value"] != model or int(current_dim["value"]) != dimension:
                raise StorageError(
                    "VALIDATION",
                    "Embedding model or dimension does not match the index.",
                )
            try:
                self._conn.execute(
                    """
                    INSERT INTO embeddings (chunk_id, model, dimension, vector, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        model = excluded.model,
                        dimension = excluded.dimension,
                        vector = excluded.vector,
                        created_at = excluded.created_at
                    """,
                    (chunk_id, model, dimension, vector, created_at),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def embeddings_complete(self, document_id: str) -> bool:
        with self._lock:
            chunks = self._conn.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            embedded = self._conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM embeddings
                WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)
                """,
                (document_id,),
            ).fetchone()
        total = int(chunks["n"])
        return total == 0 or total == int(embedded["n"])

    def iter_search_rows(
        self,
        project_id: str,
        *,
        document_id: str | None = None,
        file_type: str | None = None,
        batch_size: int = 64,
    ):
        filters = ["c.project_id = ?"]
        params: list[object] = [project_id]
        if document_id:
            filters.append("c.document_id = ?")
            params.append(document_id)
        if file_type:
            filters.append("d.file_type = ?")
            params.append(file_type)
        where = " AND ".join(filters)
        offset = 0
        while True:
            sql = f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.section,
                    c.page,
                    c.line_start,
                    c.line_end,
                    c.text,
                    d.filename,
                    e.vector,
                    e.dimension
                FROM embeddings e
                JOIN chunks c ON c.id = e.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE {where}
                ORDER BY c.document_id, c.chunk_index
                LIMIT ? OFFSET ?
            """
            with self._lock:
                rows = self._conn.execute(sql, [*params, batch_size, offset]).fetchall()
            if not rows:
                break
            for row in rows:
                yield dict(row)
            offset += batch_size

    def embedding_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()
        return int(row["n"])

    def clear_embeddings(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM embeddings")
            self._conn.execute(
                "DELETE FROM index_meta WHERE key IN ('embedding_model', 'embedding_dimension')"
            )
            self._conn.commit()

    def delete_document(self, project_id: str, document_id: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM documents WHERE id = ? AND project_id = ?",
                (document_id, project_id),
            ).fetchone()
            if row is None:
                raise StorageError("NOT_FOUND", "Document is not in this project.")
            self._conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            self._conn.commit()
