"""Custom Memoria MCP server. Thin adapter over core storage and retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from core.errors import StorageError
from core.retrieval.search import search_documents
from core.safety import check_project_id
from ingestion.indexing.pipeline import index_document, index_project
from mcp_server.context import ServerContext, open_context
from mcp_server.envelope import err, ok, run_tool

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)


def build_server(data_root: Path, embedder=None, context: ServerContext | None = None) -> MCPServer:
    ctx = context or open_context(data_root, embedder)
    mcp = MCPServer(
        "memoria",
        instructions="Harbor knowledge tools. Closed vault. No filesystem paths.",
    )

    @mcp.tool(name="memory.search", annotations=READ)
    def memory_search(
        project_id: str,
        query: str,
        types: list[str] | None = None,
        limit: int = 5,
    ) -> str:
        def action() -> dict:
            ctx.memory.get_project(project_id)
            hits = ctx.memory.search(project_id, query, types=types, limit=limit)
            return {
                "hits": [item.model_dump(mode="json") for item in hits],
                "semantic": False,
            }

        return run_tool(action)

    @mcp.tool(name="memory.get", annotations=READ)
    def memory_get(project_id: str, id: str) -> str:
        return run_tool(lambda: ctx.memory.get_record(project_id, id).model_dump(mode="json"))

    @mcp.tool(name="memory.create", annotations=WRITE)
    def memory_create(
        project_id: str,
        record: dict[str, Any],
        expected_duplicate_behavior: str = "error",
    ) -> str:
        del expected_duplicate_behavior

        def action() -> dict:
            if any(key in record for key in ("id", "revision")):
                raise StorageError("VALIDATION", "Create must not include id or revision.")
            stored = ctx.memory.create_record(project_id, record)
            return stored.model_dump(mode="json")

        return run_tool(action)

    @mcp.tool(name="memory.update", annotations=WRITE)
    def memory_update(
        project_id: str,
        id: str,
        patch: dict[str, Any],
        expected_revision: int,
    ) -> str:
        return run_tool(
            lambda: ctx.memory.update_record(project_id, id, patch, expected_revision).model_dump(mode="json")
        )

    @mcp.tool(name="memory.delete", annotations=DELETE)
    def memory_delete(project_id: str, id: str, expected_revision: int) -> str:
        def action() -> dict:
            result = ctx.memory.delete_record(project_id, id, expected_revision)
            if result is None:
                return {"deleted": True, "id": id}
            return result.model_dump(mode="json")

        return run_tool(action)

    @mcp.tool(name="documents.search", annotations=READ)
    def documents_search(
        project_id: str,
        query: str,
        limit: int = 5,
        file_type: str | None = None,
        document_id: str | None = None,
    ) -> str:
        def action() -> dict:
            ctx.memory.get_project(project_id)
            if document_id is not None and ("/" in document_id or "\\" in document_id or ".." in document_id):
                raise StorageError("VALIDATION", "Document id is not valid.")
            hits = search_documents(
                ctx.documents,
                project_id,
                query,
                ctx.embedder,
                limit=limit,
                document_id=document_id,
                file_type=file_type,
            )
            return {"hits": [item.model_dump(mode="json") for item in hits]}

        return run_tool(action)

    @mcp.tool(name="documents.get", annotations=READ)
    def documents_get(project_id: str, document_id: str, include_text: bool = False) -> str:
        def action() -> dict:
            ctx.memory.get_project(project_id)
            if "/" in document_id or "\\" in document_id or ".." in document_id:
                raise StorageError("VALIDATION", "Document id is not valid.")
            meta = ctx.documents.get(project_id, document_id)
            chunks = ctx.documents.list_chunks(project_id, document_id)
            locations = [
                {
                    "chunk_id": row["id"],
                    "chunk_index": row["chunk_index"],
                    "section": row["section"],
                    "page": row["page"],
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                    **({"text": row["text"]} if include_text else {}),
                }
                for row in (chunks[:20] if include_text else chunks)
            ]
            payload = meta.model_dump(mode="json")
            payload["chunks"] = locations
            return payload

        return run_tool(action)

    @mcp.tool(name="documents.list", annotations=READ)
    def documents_list(project_id: str) -> str:
        def action() -> dict:
            ctx.memory.get_project(project_id)
            rows = ctx.documents.list(project_id)
            return {
                "documents": [
                    {
                        "id": item.id,
                        "filename": item.filename,
                        "file_type": item.file_type,
                        "status": item.status,
                        "chunk_count": item.chunk_count,
                        "indexed_at": item.indexed_at,
                        "error": item.error,
                    }
                    for item in rows
                ]
            }

        return run_tool(action)

    @mcp.tool(name="documents.reindex", annotations=WRITE)
    def documents_reindex(
        project_id: str,
        document_id: str | None = None,
        force: bool = False,
    ) -> str:
        def action() -> dict:
            ctx.memory.get_project(project_id)
            if document_id:
                if "/" in document_id or "\\" in document_id or ".." in document_id:
                    raise StorageError("VALIDATION", "Document id is not valid.")
                report = index_document(
                    ctx.root,
                    project_id,
                    document_id,
                    force=force,
                    documents=ctx.documents,
                    embedder=ctx.embedder,
                )
            else:
                report = index_project(
                    ctx.root,
                    project_id,
                    force=force,
                    documents=ctx.documents,
                    embedder=ctx.embedder,
                )
            return {
                "unchanged": report.unchanged,
                "reindexed": report.reindexed,
                "failed": report.failed,
                "empty": report.empty,
                "unsupported": report.unsupported,
                "errors": report.errors,
            }

        return run_tool(action)

    @mcp.tool(name="project.get_status", annotations=READ)
    def project_get_status(project_id: str) -> str:
        def action() -> dict:
            record = ctx.memory.get_record(project_id, f"status_{project_id}")
            path = ctx.root / "memory" / "projects" / project_id / "status.md"
            markdown = path.read_text(encoding="utf-8") if path.exists() else ""
            return {"record": record.model_dump(mode="json"), "markdown": markdown}

        return run_tool(action)

    @mcp.tool(name="project.update_status", annotations=WRITE)
    def project_update_status(
        project_id: str,
        summary: str,
        phase: str,
        expected_revision: int,
        blockers: list[str] | None = None,
    ) -> str:
        def action() -> dict:
            record = ctx.memory.get_record(project_id, f"status_{project_id}")
            updated = ctx.memory.update_record(
                project_id,
                record.id,
                {"summary": summary, "phase": phase, "blockers": blockers or []},
                expected_revision,
            )
            return updated.model_dump(mode="json")

        return run_tool(action)

    @mcp.resource("project://{project_id}/status", mime_type="text/markdown")
    def resource_status(project_id: str) -> str:
        check_project_id(project_id)
        path = ctx.root / "memory" / "projects" / project_id / "status.md"
        if not path.exists():
            raise StorageError("NOT_FOUND", "Project status was not found.")
        return path.read_text(encoding="utf-8")

    @mcp.resource("project://{project_id}/decisions", mime_type="text/markdown")
    def resource_decisions(project_id: str) -> str:
        check_project_id(project_id)
        path = ctx.root / "memory" / "projects" / project_id / "decisions.md"
        if not path.exists():
            raise StorageError("NOT_FOUND", "Project decisions were not found.")
        return path.read_text(encoding="utf-8")

    @mcp.resource("project://{project_id}/knowledge", mime_type="text/markdown")
    def resource_knowledge(project_id: str) -> str:
        records = ctx.memory.list_records(project_id, types=["knowledge"], status="active")
        lines = ["# Knowledge", ""]
        for record in records:
            lines.extend([f"## {record.id}", "", getattr(record, "body", ""), ""])
        return "\n".join(lines)

    @mcp.resource("project://{project_id}/memory", mime_type="application/json")
    def resource_memory(project_id: str) -> str:
        records = ctx.memory.list_records(project_id, status="active")
        catalog = [
            {
                "id": item.id,
                "type": item.type,
                "topic": getattr(item, "topic", None) or getattr(item, "title", None),
                "updated_at": item.updated_at,
            }
            for item in records
        ]
        return json.dumps(catalog)

    @mcp.resource("document://{document_id}", mime_type="application/json")
    def resource_document(document_id: str) -> str:
        if "/" in document_id or "\\" in document_id or ".." in document_id:
            raise StorageError("VALIDATION", "Document id is not valid.")
        for project in ctx.memory.list_projects():
            try:
                meta = ctx.documents.get(project.id, document_id)
            except StorageError:
                continue
            chunks = ctx.documents.list_chunks(project.id, document_id)
            payload = meta.model_dump(mode="json")
            payload["chunks"] = [
                {
                    "chunk_id": row["id"],
                    "section": row["section"],
                    "page": row["page"],
                    "line_start": row["line_start"],
                    "line_end": row["line_end"],
                }
                for row in chunks
            ]
            return json.dumps(payload)
        raise StorageError("NOT_FOUND", "Document was not found.")

    @mcp.resource("conversation://{conversation_id}", mime_type="application/json")
    def resource_conversation(conversation_id: str) -> str:
        if "/" in conversation_id or "\\" in conversation_id or ".." in conversation_id:
            raise StorageError("VALIDATION", "Conversation id is not valid.")
        for project in ctx.memory.list_projects():
            try:
                conversation = ctx.memory.conversations.load(project.id, conversation_id)
            except StorageError:
                continue
            return json.dumps(conversation.model_dump(mode="json"))
        raise StorageError("NOT_FOUND", "Conversation was not found.")

    mcp._memoria_context = ctx  # type: ignore[attr-defined]
    return mcp
