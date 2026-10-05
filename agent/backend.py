"""Retrieval backend protocol. Implementations live outside writer imports."""

from __future__ import annotations

from typing import Any, Protocol


class KnowledgeBackend(Protocol):
    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...

    def search_documents(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...
