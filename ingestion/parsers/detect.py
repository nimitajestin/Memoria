"""Identify a vault original by extension. Source files are never executed."""

from __future__ import annotations

from pathlib import Path

from core.errors import StorageError

EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".docx": "docx",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".java": "java",
    ".json": "source",
    ".yaml": "source",
    ".yml": "source",
    ".toml": "source",
    ".rs": "source",
    ".go": "source",
    ".rb": "source",
    ".css": "source",
    ".html": "source",
    ".sh": "source",
    ".sql": "source",
}

CODE_TYPES = {"python", "javascript", "typescript", "c", "cpp", "java", "source"}


def detect_type(path: Path) -> str:
    kind = EXTENSIONS.get(path.suffix.lower())
    if kind is None:
        raise StorageError("UNSUPPORTED", "File type is not in the ingestion allowlist.")
    return kind
