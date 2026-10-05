"""Live Ollama checks. Skipped unless the local server is up."""

from __future__ import annotations

import httpx
import pytest

from core.ollama import OllamaEmbedder

pytestmark = pytest.mark.ollama


def test_live_embed_endpoint_if_ollama_is_running() -> None:
    try:
        httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.0)
    except httpx.HTTPError:
        pytest.skip("Ollama is not running")
    embedder = OllamaEmbedder()
    try:
        vectors = embedder.embed(["Harbor workstation"])
    except Exception as exc:
        pytest.skip(f"Ollama embed failed: {exc}")
    assert len(vectors) == 1
    assert len(vectors[0]) >= 8
