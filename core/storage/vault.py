"""Atomic YAML and JSON writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml
from pydantic import BaseModel

from core.errors import StorageError


def canonical_bytes(model: BaseModel) -> bytes:
    payload = model.model_dump(mode="json")
    text = yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10000,
    )
    if not text.endswith("\n"):
        text += "\n"
    return text.replace("\r\n", "\n").encode("utf-8")


def canonical_json(model: BaseModel) -> bytes:
    payload = model.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_yaml(path: Path) -> dict:
    try:
        loaded = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as exc:
        raise StorageError("MALFORMED", "YAML could not be parsed.") from exc
    if not isinstance(loaded, dict):
        raise StorageError("MALFORMED", "YAML root must be a mapping.")
    return loaded


def read_json(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StorageError("MALFORMED", "JSON could not be parsed.") from exc
    if not isinstance(loaded, dict):
        raise StorageError("MALFORMED", "JSON root must be an object.")
    return loaded


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise StorageError("FORBIDDEN", "Refusing to write through a symlink.")
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def commit_files(writes: list[tuple[Path, bytes]]) -> list[tuple[Path, bytes | None]]:
    """Replace each path. On failure, restore the paths already written."""

    previous: list[tuple[Path, bytes | None]] = []
    try:
        for path, data in writes:
            if path.is_symlink():
                raise StorageError("FORBIDDEN", "Refusing to write through a symlink.")
            old = path.read_bytes() if path.exists() else None
            previous.append((path, old))
            atomic_write(path, data)
    except Exception:
        restore_files(previous)
        raise
    return previous


def restore_files(previous: list[tuple[Path, bytes | None]]) -> None:
    for path, old in reversed(previous):
        if old is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, old)
