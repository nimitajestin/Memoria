from unittest.mock import Mock

import pytest

from agent.llm import PURPOSE_ANSWER, PURPOSE_ROUTE, OllamaChat
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


def test_ollama_chat_caps_context_and_keeps_model_loaded(monkeypatch) -> None:
    captured: dict = {}

    def fake_get(url, timeout):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"models": [{"name": "phi3:mini"}]}
        return response

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"message": {"content": "{\"route\":\"memory\"}"}}
        return response

    monkeypatch.setattr("agent.llm.httpx.get", fake_get)
    monkeypatch.setattr("agent.llm.httpx.post", fake_post)
    chat = OllamaChat(base_url="http://127.0.0.1:11434", model="phi3:mini", timeout=90, load_timeout=180)
    assert chat.complete(PURPOSE_ROUTE, "route", "RAM?") == "{\"route\":\"memory\"}"
    assert captured["timeout"] == 90
    options = captured["json"]["options"]
    assert options["num_ctx"] == 1024
    assert options["num_predict"] == 64
    assert captured["json"]["keep_alive"] == "10m"
    assert captured["json"]["format"] == "json"

    chat.complete(PURPOSE_ANSWER, "answer", "evidence")
    answer_options = captured["json"]["options"]
    assert answer_options["num_ctx"] == 1024
    assert answer_options["num_predict"] == 80


def test_ollama_chat_loads_a_cold_model_before_inference(monkeypatch) -> None:
    posts: list[dict] = []

    def fake_get(url, timeout):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"models": []}
        return response

    def fake_post(url, json, timeout):
        posts.append({"timeout": timeout, "predict": json["options"]["num_predict"]})
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"message": {"content": "{\"route\":\"memory\"}"}}
        return response

    monkeypatch.setattr("agent.llm.httpx.get", fake_get)
    monkeypatch.setattr("agent.llm.httpx.post", fake_post)
    chat = OllamaChat(base_url="http://127.0.0.1:11434", model="phi3:mini", timeout=90, load_timeout=180)
    assert chat.complete(PURPOSE_ROUTE, "route", "RAM?") == "{\"route\":\"memory\"}"
    assert posts[0] == {"timeout": 180, "predict": 1}
    assert posts[1]["timeout"] == 90
    assert posts[1]["predict"] == 64


def test_ollama_embedder_maps_connection_failure(monkeypatch) -> None:
    import httpx

    def fake_post(url, json, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr("core.ollama.httpx.post", fake_post)
    embedder = OllamaEmbedder(base_url="http://127.0.0.1:9", model="nomic-embed-text")
    with pytest.raises(StorageError) as caught:
        embedder.embed(["x"])
    assert caught.value.code == "FAILED_DEPENDENCY"
