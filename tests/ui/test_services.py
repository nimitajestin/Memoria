from pathlib import Path

from app.ui.services import chat_turn, in_process_system_c, list_documents, list_memory, list_projects
from core.retrieval.hash_embedder import HashEmbedder
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from ingestion.indexing.pipeline import index_project


def test_ui_lists_and_chat_share_the_vault(tmp_path: Path) -> None:
    load_harbor(tmp_path)
    index_project(tmp_path, HARBOR, embedder=HashEmbedder())
    projects = list_projects(tmp_path)
    assert any(item["id"] == HARBOR for item in projects)
    memory = list_memory(tmp_path, HARBOR)
    assert any(item["id"] == "decision_a11ce0000001" for item in memory)
    documents = list_documents(tmp_path, HARBOR)
    assert documents
    result = chat_turn(tmp_path, HARBOR, "How much RAM does the Harbor workstation have?", system="B")
    assert result.answer
    assert result.trace
    c = in_process_system_c(tmp_path, HARBOR, "What architecture did I decide for the retrieval system?")
    assert c.route == "memory"
