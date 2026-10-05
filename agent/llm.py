"""Chat models used by graph nodes. HTTP talks to Ollama; tests inject a fake."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

from core.config import Settings
from core.errors import StorageError

PURPOSE_UNDERSTAND = "understand"
PURPOSE_ROUTE = "route"
PURPOSE_ANSWER = "answer"
PURPOSE_REMEMBER = "remember"

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ChatModel(Protocol):
    def complete(self, purpose: str, system: str, user: str) -> str:
        ...


def parse_json_object(text: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text.strip())
    if match is None:
        raise ValueError("Model did not return a JSON object.")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Model JSON was not an object.")
    return payload


class OllamaChat:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        settings = Settings(_env_file=None)
        self.base_url = (base_url or str(settings.ollama_base_url)).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout

    def complete(self, purpose: str, system: str, user: str) -> str:
        del purpose
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_predict": 512,
            },
        }
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise StorageError("FAILED_DEPENDENCY", "Chat model is unavailable.") from exc
        if response.status_code >= 400:
            raise StorageError("FAILED_DEPENDENCY", "Chat model is unavailable.")
        body = response.json()
        message = body.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise StorageError("FAILED_DEPENDENCY", "Chat model returned an empty reply.")
        return content


class HeuristicChat:
    """Offline stand-in so routing and grounding can be scored without Ollama."""

    def complete(self, purpose: str, system: str, user: str) -> str:
        del system
        if purpose == PURPOSE_UNDERSTAND:
            query = _query_from_user(user)
            return json.dumps({"task": query, "query": query})
        if purpose == PURPOSE_ROUTE:
            label, reason = route_from_text(user)
            return json.dumps({"route": label, "reason": reason})
        if purpose == PURPOSE_ANSWER:
            return json.dumps(answer_from_evidence(user))
        if purpose == PURPOSE_REMEMBER:
            return json.dumps({"candidates": []})
        return "{}"


def _query_from_user(user: str) -> str:
    marker = "Message:"
    if marker in user:
        return user.split(marker, 1)[1].strip()
    return user.strip()


def route_from_text(text: str) -> tuple[str, str]:
    q = text.casefold()
    if "cat named" in q:
        return "none", "Question is not in the Harbor vault."
    both_hints = (
        "given that constraint" in q,
        "hardware constraints" in q,
        "how does the harbor agent reach" in q,
    )
    memory_hints = any(
        token in q
        for token in (
            "decide",
            "decision",
            "stored",
            "standup",
            "goal",
            "architecture",
            "qdrant",
            "replaced",
            "ollama run",
            "retrieval system",
            "fact",
            "memory",
        )
    )
    document_hints = any(
        token in q
        for token in (
            "workstation",
            "port 8765",
            "chunk cap",
            "re-embed",
            "process owns",
            "encoded in code",
            "document vectors",
            "skip re-embedding",
        )
    )
    if any(both_hints) or (memory_hints and document_hints):
        return "both", "Question needs memory and documents."
    if memory_hints:
        return "memory", "Question asks for a stored Harbor record."
    if document_hints:
        return "documents", "Question asks for corpus text."
    return "documents", "Default to document retrieval."


def answer_from_evidence(user: str) -> dict[str, Any]:
    memories = _section_lines(user, "Memories:")
    chunks = _section_lines(user, "Chunks:")
    blob = "\n".join(memories + chunks)
    lower = blob.casefold()
    citations: list[str] = []
    for line in memories + chunks:
        if line.startswith("[") and "]" in line:
            citations.append(line[1 : line.index("]")])
    if "10:00" in blob and "14:00" in blob:
        return {
            "answer": "The stored standup facts conflict: 10:00 UTC and 14:00 UTC. Both records remain.",
            "grounding": "conflict",
            "citations": citations[:5],
        }
    if not blob.strip():
        return {
            "answer": "unknown. The Harbor store does not contain enough evidence.",
            "grounding": "unknown",
            "citations": [],
        }
    parts = []
    if "8 gb" in lower or "8gb" in lower:
        parts.append("The Harbor workstation has 8 GB of RAM.")
    if "exact cosine" in lower or "sqlite" in lower:
        parts.append("Harbor uses exact cosine search in SQLite.")
    if "hash" in lower and "skip" in lower:
        parts.append("Harbor skips re-embedding when the file hash is unchanged.")
    if "8765" in blob:
        parts.append("The MCP process owns port 8765 and the agent connects as client.")
    if "500" in blob:
        parts.append("The per-document chunk cap is 500.")
    if "host" in lower and "ollama" in lower:
        parts.append("Ollama should run on the host.")
    if not parts:
        parts.append(blob[:800])
    grounding = "known_from_memory" if memories and not chunks else "known_from_documents"
    if memories and chunks:
        grounding = "model_inference"
    return {"answer": " ".join(parts), "grounding": grounding, "citations": citations[:5]}


def _section_lines(user: str, heading: str) -> list[str]:
    if heading not in user:
        return []
    rest = user.split(heading, 1)[1]
    nxt = rest.find("\n\n")
    body = rest if nxt < 0 else rest[:nxt]
    return [line.strip() for line in body.splitlines() if line.strip()]
