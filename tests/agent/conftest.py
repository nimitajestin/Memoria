from pathlib import Path

from core.retrieval.hash_embedder import HashEmbedder
from evaluation.datasets.controlled.load import HARBOR, load_harbor, load_questions
from ingestion.indexing.pipeline import index_project
from mcp_server.server import build_server


def harbor_stack(tmp_path: Path):
    loaded = load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    questions = {item.id: item for item in load_questions()}
    server = build_server(tmp_path, embedder)
    return loaded, embedder, questions, server
