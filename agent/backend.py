"""Retrieval backend protocol. Implementations live outside writer imports."""

from __future__ import annotations

from typing import Any, Protocol


class KnowledgeBackend(Protocol):
    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...

    def search_documents(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...

    def policy_records(self, project_id: str) -> list[Any]:
        ...

    def create_memory(self, project_id: str, record: dict[str, Any]) -> dict[str, Any]:
        ...

    def update_memory(
        self,
        project_id: str,
        record_id: str,
        patch: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        ...
