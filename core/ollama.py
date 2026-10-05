"""Ollama HTTP client. Chat and embeddings stay on the host."""

from __future__ import annotations

import httpx

from core.config import Settings
from core.errors import StorageError


class OllamaEmbedder:
    """POST /api/embed. Unloads the embedding model after each batch."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        settings = Settings(_env_file=None)
        self.base_url = (base_url or str(settings.ollama_base_url)).rstrip("/")
        self.model = model or settings.embedding_model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": texts, "keep_alive": 0}
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise StorageError("FAILED_DEPENDENCY", "Embedding model is unavailable.") from exc
        if response.status_code >= 400:
            raise StorageError("FAILED_DEPENDENCY", "Embedding model is unavailable.")
        body = response.json()
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise StorageError("FAILED_DEPENDENCY", "Embedding response did not match the batch.")
        return [[float(value) for value in row] for row in vectors]
