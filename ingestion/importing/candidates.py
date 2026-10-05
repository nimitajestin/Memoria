"""Turn user transcript lines into memory candidates for the policy."""

from __future__ import annotations

from core.schemas.conversations import Turn

CASUAL = (
    "pizza",
    "cat named",
    "do not put",
    "not a project fact",
    "not stable",
    "yesterday",
)


def extract_candidates(turns: list[Turn]) -> list[dict]:
    candidates: list[dict] = []
    for turn in turns:
        if turn.role != "user":
            continue
        text = turn.content.strip()
        if len(text) < 12:
            continue
        lower = text.casefold()
        durable = not any(token in lower for token in CASUAL)
        topic = "imported"
        if "ollama" in lower:
            topic = "runtime"
        elif "sqlite" in lower or "retrieval" in lower:
            topic = "retrieval"
        candidates.append(
            {
                "type": "fact",
                "confidence": 0.85 if durable else 0.9,
                "stable": durable,
                "project_specific": durable,
                "future_useful": durable,
                "source_kind": "user",
                "topic": topic,
                "statement": text[:8000],
            }
        )
    return candidates
