"""Identifiers, vault paths, and the per-project file lock."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from core.errors import StorageError

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
REF_RE = re.compile(
    r"^(fact|decision|goal|knowledge|episode|summary|chunk|doc|conv)_[0-9a-f]{12}$"
)

PREFIX_BY_TYPE = {
    "fact": "fact",
    "decision": "decision",
    "goal": "goal",
    "knowledge": "knowledge",
    "episode": "episode",
    "conversation_summary": "summary",
    "status": "status",
}

TYPE_DIRS = {
    "fact": "facts",
    "decision": "decisions",
    "goal": "goals",
    "knowledge": "knowledge",
    "episode": "episodes",
    "conversation_summary": "summaries",
}

ACTIVE_CAPS = {
    "fact": 200,
    "decision": 100,
    "goal": 200,
    "knowledge": 200,
    "episode": 200,
    "conversation_summary": 200,
    "status": 1,
}


def check_project_id(value: str) -> str:
    if not isinstance(value, str) or ".." in value or "/" in value or "\\" in value:
        raise StorageError("FORBIDDEN", "Project id escapes the vault.")
    if PROJECT_ID_RE.fullmatch(value) is None:
        raise StorageError("VALIDATION", "Project id is not valid.")
    return value


def new_record_id(record_type: str) -> str:
    prefix = PREFIX_BY_TYPE[record_type]
    if record_type == "status":
        raise StorageError("VALIDATION", "Status ids are derived from the project id.")
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def status_record_id(project_id: str) -> str:
    return f"status_{check_project_id(project_id)}"


def check_record_id(record_type: str, record_id: str) -> str:
    if record_type == "status":
        if re.fullmatch(r"^status_[a-z0-9][a-z0-9_-]{0,63}$", record_id) is None:
            raise StorageError("VALIDATION", "Status id is not valid.")
        return record_id
    prefix = PREFIX_BY_TYPE.get(record_type)
    if prefix is None or re.fullmatch(rf"^{prefix}_[0-9a-f]{{12}}$", record_id) is None:
        raise StorageError("VALIDATION", "Record id is not valid.")
    return record_id


def check_ref(value: str) -> str:
    if REF_RE.fullmatch(value) is None:
        raise StorageError("VALIDATION", "Reference id is not valid.")
    return value


def safe_filename(name: str) -> str:
    if not isinstance(name, str) or name != Path(name).name or name in {".", ".."}:
        raise StorageError("FORBIDDEN", "Filename is not a single path segment.")
    if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", name) is None:
        raise StorageError("VALIDATION", "Filename contains unsupported characters.")
    return name


def resolve_inside(root: Path, path: Path) -> Path:
    """Return path only when it stays inside root after symlink resolution."""

    root_resolved = root.resolve()
    parent = path.parent
    if parent.exists():
        parent_resolved = parent.resolve()
    else:
        parent_resolved = Path(os.path.abspath(parent))
    if not parent_resolved.is_relative_to(root_resolved):
        raise StorageError("FORBIDDEN", "Path escapes the data root.")
    full = parent_resolved / path.name
    cursor = root_resolved
    try:
        relative = full.relative_to(root_resolved)
    except ValueError as exc:
        raise StorageError("FORBIDDEN", "Path escapes the data root.") from exc
    for part in relative.parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise StorageError("FORBIDDEN", "Symlinks are not allowed inside the vault.")
    if full.is_symlink() or path.is_symlink():
        raise StorageError("FORBIDDEN", "Symlinks are not allowed inside the vault.")
    if full.exists() and not full.resolve().is_relative_to(root_resolved):
        raise StorageError("FORBIDDEN", "Path escapes the data root.")
    return full


class FileLock:
    """Exclusive lock on one lock file. Not re-entrant on the same thread."""

    def __init__(self, path: Path, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fh = None
        self._locked = False

    def __enter__(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+b")
        try:
            self._fh.seek(0, os.SEEK_END)
            if self._fh.tell() == 0:
                self._fh.write(b"\0")
                self._fh.flush()
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    self._fh.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._locked = True
                    return self
                except OSError:
                    if time.monotonic() >= deadline:
                        raise StorageError("CONFLICT", "Timed out waiting for the project lock.")
                    time.sleep(0.02)
        except Exception:
            self._fh.close()
            self._fh = None
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fh is None:
            return
        try:
            if self._locked:
                self._fh.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
            self._locked = False
