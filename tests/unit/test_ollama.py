from unittest.mock import Mock

import pytest

from core.errors import StorageError
from core.ollama import OllamaEmbedder


def test_ollama_embedder_sends_keep_alive_zero(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        return response

    monkeypatch.setattr("core.ollama.httpx.post", fake_post)
    embedder = OllamaEmbedder(base_url="http://127.0.0.1:11434", model="nomic-embed-text")
    vectors = embedder.embed(["Harbor RAM"])
    assert captured["url"].endswith("/api/embed")
    assert captured["json"]["keep_alive"] == 0
    assert captured["json"]["model"] == "nomic-embed-text"
    assert vectors == [[0.1, 0.2, 0.3]]


def test_ollama_embedder_maps_connection_failure(monkeypatch) -> None:
    import httpx

    def fake_post(url, json, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("core.ollama.httpx.post", fake_post)
    embedder = OllamaEmbedder(base_url="http://127.0.0.1:9", model="nomic-embed-text")
    with pytest.raises(StorageError) as caught:
        embedder.embed(["x"])
    assert caught.value.code == "FAILED_DEPENDENCY"
