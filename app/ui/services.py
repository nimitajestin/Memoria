"""Vault helpers for Streamlit screens. Chat mutations use the agent graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.graph.build import build_graph, run_turn
from agent.llm import HeuristicChat, OllamaChat
from agent.mcp_client import MCPBackend
from agent.state.schema import TurnResult
from core.config import Settings
from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import run_direct
from mcp_server.server import build_server


def open_repos(data_root: Path):
    memory = MemoryRepository(data_root)
    documents = DocumentRepository(data_root, memory.index)
    return memory, documents


def list_projects(data_root: Path) -> list[dict[str, Any]]:
    memory, documents = open_repos(data_root)
    try:
        return [item.model_dump(mode="json") for item in memory.list_projects()]
    finally:
        documents.close()
        memory.close()


def list_memory(data_root: Path, project_id: str) -> list[dict[str, Any]]:
    memory, documents = open_repos(data_root)
    try:
        return [item.model_dump(mode="json") for item in memory.list_records(project_id)]
    finally:
        documents.close()
        memory.close()


def list_documents(data_root: Path, project_id: str) -> list[dict[str, Any]]:
    memory, documents = open_repos(data_root)
    try:
        return [item.model_dump(mode="json") for item in documents.list(project_id)]
    finally:
        documents.close()
        memory.close()


def chat_turn(
    data_root: Path,
    project_id: str,
    message: str,
    *,
    system: str = "B",
    live_ollama: bool = False,
    prior_turns: list[dict[str, str]] | None = None,
) -> TurnResult:
    llm = OllamaChat() if live_ollama else HeuristicChat()
    if system == "C":
        settings = Settings(_env_file=None)
        backend = MCPBackend(url=str(settings.mcp_url))
        graph = build_graph(backend, llm, data_root=data_root)
        return run_turn(
            graph,
            project_id=project_id,
            message=message,
            prior_turns=prior_turns,
            thread_id="ui",
        )
    memory, documents = open_repos(data_root)
    try:
        return run_direct(
            project_id=project_id,
            message=message,
            memory=memory,
            documents=documents,
            embedder=HashEmbedder(),
            llm=llm,
            prior_turns=prior_turns,
            thread_id="ui-b",
        )
    finally:
        documents.close()
        memory.close()


def in_process_system_c(
    data_root: Path,
    project_id: str,
    message: str,
) -> TurnResult:
    memory, documents = open_repos(data_root)
    try:
        server = build_server(data_root, HashEmbedder())
        graph = build_graph(MCPBackend(server=server), HeuristicChat(), data_root=data_root)
        return run_turn(graph, project_id=project_id, message=message, thread_id="ui-c")
    finally:
        documents.close()
        memory.close()
