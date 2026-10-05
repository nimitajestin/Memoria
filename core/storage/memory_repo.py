"""YAML memory vault, SQLite index, and memory CRUD."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from core.errors import StorageError
from core.logging import log_event
from core.memory.content import fingerprint, searchable_text, sha256_bytes, title_or_topic
from core.memory.policy import PolicyRecord, structural_disposition
from core.safety import (
    ACTIVE_CAPS,
    TYPE_DIRS,
    FileLock,
    check_project_id,
    check_record_id,
    new_record_id,
    resolve_inside,
    status_record_id,
)
from core.schemas.memory import (
    DRAFT_ADAPTER,
    MUTABLE_FIELDS,
    DecisionRecord,
    MemoryHit,
    ProjectFile,
    Source,
    StatusRecord,
    parse_record,
    utc_now,
)
from core.storage.conversations import ConversationStore
from core.storage.db import IndexDatabase
from core.storage.projections import render_decisions, render_status
from core.storage.vault import (
    canonical_bytes,
    commit_files,
    read_yaml,
    restore_files,
)


def _type_by_prefix() -> dict[str, str]:
    from core.safety import PREFIX_BY_TYPE

    return {prefix: kind for kind, prefix in PREFIX_BY_TYPE.items()}


class MemoryRepository:
    """Human-readable project memory. YAML is the source of truth."""

    def __init__(
        self,
        data_root: Path,
        index: IndexDatabase | None = None,
        caps: dict[str, int] | None = None,
    ) -> None:
        self.root = Path(data_root).resolve()
        self.index = index or IndexDatabase(self.root / "index" / "memoria.sqlite")
        self._owns_index = index is None
        self.caps = dict(ACTIVE_CAPS)
        if caps:
            self.caps.update(caps)
        self.conversations = ConversationStore(self.root)
        self._prefixes = _type_by_prefix()

    def close(self) -> None:
        if self._owns_index:
            self.index.close()

    def __enter__(self) -> MemoryRepository:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_project(self, project_id: str, name: str, description: str = "") -> ProjectFile:
        project_id = check_project_id(project_id)
        directory = self._project_dir(project_id)
        if directory.is_symlink():
            raise StorageError("FORBIDDEN", "Symlinks are not allowed inside the vault.")
        directory.mkdir(parents=True, exist_ok=True)
        with FileLock(directory / ".lock"):
            if (directory / "project.yaml").exists():
                raise StorageError("CONFLICT", "Project already exists.")
            now = utc_now()
            try:
                project = ProjectFile(
                    id=project_id,
                    name=name,
                    description=description,
                    created_at=now,
                    updated_at=now,
                )
                status = StatusRecord(
                    id=status_record_id(project_id),
                    type="status",
                    project_id=project_id,
                    created_at=now,
                    updated_at=now,
                    status="active",
                    revision=1,
                    phase="new",
                    summary="Project created.",
                    blockers=[],
                    source=Source(),
                    created_by="user",
                )
            except ValidationError as exc:
                raise StorageError("VALIDATION", "Project failed schema validation.") from exc
            status_path = directory / "status.yaml"
            writes = [
                (directory / "project.yaml", canonical_bytes(project)),
                (status_path, canonical_bytes(status)),
                (directory / "status.md", render_status(status).encode("utf-8")),
                (directory / "decisions.md", render_decisions([]).encode("utf-8")),
            ]
            previous = commit_files(writes)
            try:
                self.index.update_memory_rows(
                    [self._index_row(status, status_path, sha256_bytes(writes[1][1]))],
                    [],
                )
            except Exception:
                restore_files(previous)
                raise
        log_event(self.root, "project_create", project_id=project_id, record_id=status.id, record_type="status")
        return project

    def list_projects(self) -> list[ProjectFile]:
        base = self.root / "memory" / "projects"
        if not base.exists():
            return []
        found: list[ProjectFile] = []
        for directory in sorted(path for path in base.iterdir() if path.is_dir()):
            try:
                check_project_id(directory.name)
                found.append(self.get_project(directory.name))
            except StorageError:
                continue
        return found

    def get_project(self, project_id: str) -> ProjectFile:
        directory = self._require_project(project_id)
        try:
            return ProjectFile.model_validate(read_yaml(directory / "project.yaml"))
        except ValidationError as exc:
            raise StorageError("MALFORMED", "project.yaml failed schema validation.") from exc
        except StorageError:
            raise

    def create_record(self, project_id: str, payload: dict):
        project_id = check_project_id(project_id)
        directory = self._require_project(project_id)
        with FileLock(directory / ".lock"):
            draft = self._parse_draft(payload)
            if draft.project_id is not None and draft.project_id != project_id:
                raise StorageError("VALIDATION", "Record project_id does not match the request.")
            if draft.supersedes and draft.type != "decision":
                raise StorageError("VALIDATION", "Only a decision can set supersedes.")
            record = self._materialize(project_id, draft)
            self._check_quote(project_id, record.source)
            self._check_conflict_ids(project_id, record.conflicts_with)
            snapshots = self._snapshots(project_id, record.type)
            digest, identity, topic = fingerprint(record.type, record.model_dump())
            result = structural_disposition(
                record_type=record.type,
                topic=topic,
                content_digest=digest,
                identity_digest=identity,
                supersedes=record.supersedes,
                existing=snapshots,
                cap=self.caps[record.type],
            )
            if result.outcome == "reject":
                raise StorageError(
                    "CONFLICT",
                    result.detail or "Memory write was rejected.",
                    {"reason": result.reason, "target_id": result.target_id, "conflict_ids": result.conflict_ids},
                )
            if result.outcome == "update":
                raise StorageError(
                    "CONFLICT",
                    "An active record already matches. Update it with expected_revision.",
                    {"reason": result.reason, "target_id": result.target_id},
                )
            if result.conflict_ids:
                linked = sorted(set(record.conflicts_with) | set(result.conflict_ids))
                record = parse_record({**record.model_dump(mode="json"), "conflicts_with": linked})
            writes: list[tuple[Path, bytes]] = []
            index_rows = []
            record_path = self._record_path(directory, record)
            record_bytes = canonical_bytes(record)
            writes.append((record_path, record_bytes))
            index_rows.append(self._index_row(record, record_path, sha256_bytes(record_bytes)))
            if result.target_id:
                target = self._load_id(project_id, result.target_id)
                if target is None or target.type != "decision" or target.status != "active":
                    raise StorageError("CONFLICT", "supersedes does not name an active decision.")
                superseded = parse_record(
                    {
                        **target.model_dump(mode="json"),
                        "status": "superseded",
                        "revision": target.revision + 1,
                        "updated_at": utc_now(),
                    }
                )
                target_path = self._record_path(directory, superseded)
                target_bytes = canonical_bytes(superseded)
                writes.append((target_path, target_bytes))
                index_rows.append(self._index_row(superseded, target_path, sha256_bytes(target_bytes)))
            previous = commit_files(writes)
            view_previous: list[tuple[Path, bytes | None]] = []
            try:
                view_previous = self._write_views(project_id)
                self.index.update_memory_rows(index_rows, [])
            except Exception:
                if view_previous:
                    restore_files(view_previous)
                restore_files(previous)
                raise
        log_event(
            self.root,
            "memory_create",
            project_id=project_id,
            record_id=record.id,
            record_type=record.type,
            outcome="create",
        )
        return record

    def seed_record(self, payload: dict):
        """Write a complete record with a caller-chosen id. Used by evaluation fixtures."""

        try:
            record = parse_record(payload)
        except ValidationError as exc:
            raise StorageError("VALIDATION", "Record failed schema validation.") from exc
        check_record_id(record.type, record.id)
        directory = self._require_project(record.project_id)
        with FileLock(directory / ".lock"):
            path = self._record_path(directory, record)
            if path.exists():
                raise StorageError("CONFLICT", "A seeded record with this id already exists.")
            data = canonical_bytes(record)
            previous = commit_files([(path, data)])
            view_previous: list[tuple[Path, bytes | None]] = []
            try:
                view_previous = self._write_views(record.project_id)
                self.index.update_memory_rows(
                    [self._index_row(record, path, sha256_bytes(data))],
                    [],
                )
            except Exception:
                if view_previous:
                    restore_files(view_previous)
                restore_files(previous)
                raise
        log_event(
            self.root,
            "memory_seed",
            project_id=record.project_id,
            record_id=record.id,
            record_type=record.type,
            outcome="create",
        )
        return record

    def get_record(self, project_id: str, record_id: str):
        project_id = check_project_id(project_id)
        directory = self._require_project(project_id)
        with FileLock(directory / ".lock"):
            path = self._path_for_id(directory, project_id, record_id)
            if not path.exists():
                raise StorageError("NOT_FOUND", "Memory record was not found.")
            raw = path.read_bytes()
            digest = sha256_bytes(raw)
            record = self._parse_path(project_id, path, raw)
            if record.id != record_id:
                raise StorageError("MALFORMED", "Memory filename does not match its id.")
            row = self.index.get_memory_row(record.id)
            if row is None or row["content_hash"] != digest or row["project_id"] != project_id:
                if row is not None and row["project_id"] != project_id:
                    raise StorageError("NOT_FOUND", "Memory record was not found.")
                self.index.update_memory_rows([self._index_row(record, path, digest)], [])
            return record

    def update_record(self, project_id: str, record_id: str, patch: dict, expected_revision: int):
        project_id = check_project_id(project_id)
        directory = self._require_project(project_id)
        with FileLock(directory / ".lock"):
            current = self._load_required(project_id, record_id)
            if current.revision != expected_revision:
                raise StorageError(
                    "CONFLICT",
                    "expected_revision does not match the stored record.",
                    {"reason": "revision_mismatch", "revision": current.revision},
                )
            updated = self._apply_patch(current, patch)
            self._check_quote(project_id, updated.source)
            others = [item for item in self._snapshots(project_id, updated.type) if item.id != updated.id]
            digest, identity, topic = fingerprint(updated.type, updated.model_dump())
            result = structural_disposition(
                record_type=updated.type,
                topic=topic,
                content_digest=digest,
                identity_digest=identity,
                supersedes=None,
                existing=others,
                cap=self.caps[updated.type],
            )
            if result.outcome == "reject":
                raise StorageError(
                    "CONFLICT",
                    result.detail or "Memory update was rejected.",
                    {"reason": result.reason, "conflict_ids": result.conflict_ids},
                )
            if result.outcome == "update":
                raise StorageError(
                    "CONFLICT",
                    "The update matches a different active record.",
                    {"reason": result.reason, "target_id": result.target_id},
                )
            if result.conflict_ids:
                linked = sorted(set(updated.conflicts_with) | set(result.conflict_ids))
                updated = parse_record({**updated.model_dump(mode="json"), "conflicts_with": linked})
            path = self._record_path(directory, updated)
            data = canonical_bytes(updated)
            previous = commit_files([(path, data)])
            view_previous: list[tuple[Path, bytes | None]] = []
            try:
                view_previous = self._write_views(project_id)
                self.index.update_memory_rows([self._index_row(updated, path, sha256_bytes(data))], [])
            except Exception:
                if view_previous:
                    restore_files(view_previous)
                restore_files(previous)
                raise
        log_event(
            self.root,
            "memory_update",
            project_id=project_id,
            record_id=updated.id,
            record_type=updated.type,
            outcome="update",
        )
        return updated

    def delete_record(self, project_id: str, record_id: str, expected_revision: int):
        project_id = check_project_id(project_id)
        directory = self._require_project(project_id)
        with FileLock(directory / ".lock"):
            current = self._load_required(project_id, record_id)
            if current.revision != expected_revision:
                raise StorageError(
                    "CONFLICT",
                    "expected_revision does not match the stored record.",
                    {"reason": "revision_mismatch"},
                )
            path = self._record_path(directory, current)
            if current.type in {"decision", "status"}:
                if current.status == "withdrawn":
                    return current
                withdrawn = parse_record(
                    {
                        **current.model_dump(mode="json"),
                        "status": "withdrawn",
                        "revision": current.revision + 1,
                        "updated_at": utc_now(),
                    }
                )
                data = canonical_bytes(withdrawn)
                previous = commit_files([(path, data)])
                view_previous: list[tuple[Path, bytes | None]] = []
                try:
                    view_previous = self._write_views(project_id)
                    self.index.update_memory_rows(
                        [self._index_row(withdrawn, path, sha256_bytes(data))],
                        [],
                    )
                except Exception:
                    if view_previous:
                        restore_files(view_previous)
                    restore_files(previous)
                    raise
                result = withdrawn
            else:
                raw = path.read_bytes()
                path.unlink()
                view_previous = []
                try:
                    view_previous = self._write_views(project_id)
                    self.index.update_memory_rows([], [current.id])
                except Exception:
                    if view_previous:
                        restore_files(view_previous)
                    commit_files([(path, raw)])
                    raise
                result = None
        log_event(
            self.root,
            "memory_delete",
            project_id=project_id,
            record_id=record_id,
            record_type=current.type,
            outcome="delete",
        )
        return result

    def list_records(self, project_id: str, types: list[str] | None = None, status: str = "active") -> list:
        project_id = check_project_id(project_id)
        directory = self._require_project(project_id)
        with FileLock(directory / ".lock"):
            self._sync_index(project_id)
            records = []
            for kind in types or [*TYPE_DIRS.keys(), "status"]:
                if kind not in TYPE_DIRS and kind != "status":
                    raise StorageError("VALIDATION", "Unknown memory type.")
                if kind == "status":
                    loaded = self._try_load(directory / "status.yaml", project_id)
                    found = [loaded] if loaded is not None else []
                else:
                    found = self._load_type(directory, project_id, kind)
                records.extend(item for item in found if item.status == status)
        return sorted(records, key=lambda item: (item.type, item.updated_at, item.id))

    def search(
        self,
        project_id: str,
        query: str,
        types: list[str] | None = None,
        limit: int = 5,
    ) -> list[MemoryHit]:
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            raise StorageError("VALIDATION", "Search query must be 1 to 1000 characters.")
        if limit < 1 or limit > 5:
            raise StorageError("VALIDATION", "Search limit must be from 1 to 5.")
        records = self.list_records(project_id, types=types, status="active")
        tokens = [token for token in query.casefold().split() if token]
        hits: list[MemoryHit] = []
        for record in records:
            haystack = searchable_text(record).casefold()
            matched = sum(1 for token in tokens if token in haystack)
            if matched == 0:
                continue
            snippet = searchable_text(record)[:400]
            hits.append(
                MemoryHit(
                    id=record.id,
                    type=record.type,
                    title_or_topic=title_or_topic(record),
                    score=round(matched / len(tokens), 4),
                    snippet=snippet,
                    updated_at=record.updated_at,
                )
            )
        hits.sort(key=lambda item: (-item.score, item.updated_at, item.id))
        return hits[:limit]

    def index_entry(self, project_id: str, record_id: str) -> dict | None:
        project_id = check_project_id(project_id)
        row = self.index.get_memory_row(record_id)
        if row is None or row["project_id"] != project_id:
            return None
        return row

    def _parse_draft(self, payload: dict):
        try:
            return DRAFT_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            raise StorageError("VALIDATION", "Record failed schema validation.") from exc

    def _materialize(self, project_id: str, draft):
        now = utc_now()
        payload = draft.model_dump(mode="json")
        payload.update(
            {
                "id": new_record_id(draft.type),
                "project_id": project_id,
                "created_at": now,
                "updated_at": now,
                "status": "active",
                "revision": 1,
            }
        )
        try:
            return parse_record(payload)
        except ValidationError as exc:
            raise StorageError("VALIDATION", "Record failed schema validation.") from exc

    def _apply_patch(self, current, patch: dict):
        if not isinstance(patch, dict) or not patch:
            raise StorageError("VALIDATION", "Patch is empty.")
        if current.type == "decision" and {"decision", "reason", "topic"} & set(patch):
            raise StorageError(
                "VALIDATION",
                "Decision text cannot be overwritten. Add a new decision with supersedes.",
            )
        if current.type == "decision" and "status" in patch and patch["status"] != "withdrawn":
            raise StorageError("VALIDATION", "A decision can only move from active to withdrawn here.")
        unknown = set(patch) - MUTABLE_FIELDS[current.type]
        if unknown:
            raise StorageError(
                "VALIDATION",
                "Patch contains fields that cannot be changed.",
                {"fields": sorted(unknown)},
            )
        data = current.model_dump(mode="json")
        data.update(patch)
        data["revision"] = current.revision + 1
        data["updated_at"] = utc_now()
        try:
            updated = parse_record(data)
        except ValidationError as exc:
            raise StorageError("VALIDATION", "Patch failed schema validation.") from exc
        old = current.model_dump(mode="json")
        new = updated.model_dump(mode="json")
        if all(new[key] == old[key] for key in new if key not in {"revision", "updated_at"}):
            raise StorageError("VALIDATION", "Patch does not change the record.")
        return updated

    def _check_quote(self, project_id: str, source: Source) -> None:
        if source.ref is None:
            if source.quote:
                raise StorageError("VALIDATION", "A quote requires source.ref.")
            return
        allowed = {
            "user": ("conv_",),
            "document": ("chunk_", "doc_"),
            "conversation": ("conv_",),
            "agent": ("chunk_", "doc_", "conv_"),
            "import": ("conv_",),
        }[source.kind]
        if not source.ref.startswith(allowed):
            raise StorageError("VALIDATION", "source.ref does not match source.kind.")
        if not source.quote:
            raise StorageError("VALIDATION", "A quote is required when source.ref is set.")
        texts = self._resolve_texts(project_id, source.ref)
        if texts is None:
            raise StorageError("VALIDATION", "source.ref does not resolve to stored text.")
        if not any(source.quote in text for text in texts):
            raise StorageError("VALIDATION", "Quote is not contained in the cited text.")

    def _resolve_texts(self, project_id: str, ref: str) -> list[str] | None:
        if ref.startswith("chunk_"):
            row = self.index.get_chunk(project_id, ref)
            return [row["text"]] if row else None
        if ref.startswith("doc_"):
            texts = self.index.list_chunk_texts(project_id, ref)
            return texts or None
        if ref.startswith("conv_"):
            return self.conversations.turn_texts(project_id, ref)
        return None

    def _check_conflict_ids(self, project_id: str, ids: list[str]) -> None:
        known = {row["id"] for row in self.index.list_memory_rows(project_id)}
        for directory_type in TYPE_DIRS:
            for record in self._load_type(self._project_dir(project_id), project_id, directory_type):
                known.add(record.id)
        status = self._try_load(self._project_dir(project_id) / "status.yaml", project_id)
        if status is not None:
            known.add(status.id)
        missing = [item for item in ids if item not in known]
        if missing:
            raise StorageError("VALIDATION", "conflicts_with names a missing record.", {"ids": missing})

    def _snapshots(self, project_id: str, record_type: str) -> list[PolicyRecord]:
        directory = self._project_dir(project_id)
        if record_type == "status":
            loaded = self._try_load(directory / "status.yaml", project_id)
            records = [loaded] if loaded is not None else []
        else:
            records = self._load_type(directory, project_id, record_type)
        snapshots = []
        for record in records:
            digest, identity, topic = fingerprint(record.type, record.model_dump())
            snapshots.append(
                PolicyRecord(
                    id=record.id,
                    type=record.type,
                    topic=topic,
                    content_hash=digest,
                    identity_hash=identity,
                    revision=record.revision,
                    status=record.status,
                )
            )
        return snapshots

    def _load_required(self, project_id: str, record_id: str):
        directory = self._project_dir(project_id)
        path = self._path_for_id(directory, project_id, record_id)
        if not path.exists():
            raise StorageError("NOT_FOUND", "Memory record was not found.")
        record = self._parse_path(project_id, path, path.read_bytes())
        if record.id != record_id:
            raise StorageError("MALFORMED", "Memory filename does not match its id.")
        return record

    def _load_id(self, project_id: str, record_id: str):
        try:
            return self._load_required(project_id, record_id)
        except StorageError as exc:
            if exc.code == "NOT_FOUND":
                return None
            raise

    def _write_views(self, project_id: str) -> list[tuple[Path, bytes | None]]:
        directory = self._project_dir(project_id)
        writes: list[tuple[Path, bytes]] = []
        status = self._try_load(directory / "status.yaml", project_id)
        if isinstance(status, StatusRecord):
            writes.append((directory / "status.md", render_status(status).encode("utf-8")))
        decisions = [
            item
            for item in self._load_type(directory, project_id, "decision")
            if isinstance(item, DecisionRecord)
        ]
        writes.append((directory / "decisions.md", render_decisions(decisions).encode("utf-8")))
        return commit_files(writes)

    def _sync_index(self, project_id: str) -> None:
        directory = self._project_dir(project_id)
        rows = {row["id"]: row for row in self.index.list_memory_rows(project_id)}
        seen: set[str] = set()
        malformed: set[str] = set()
        upserts = []
        for path in self._iter_record_files(directory):
            if path.is_symlink():
                continue
            raw = path.read_bytes()
            digest = sha256_bytes(raw)
            try:
                record = self._parse_path(project_id, path, raw)
            except StorageError:
                malformed.add(path.stem)
                continue
            seen.add(record.id)
            current = rows.get(record.id)
            if (
                current is None
                or current["content_hash"] != digest
                or current["status"] != record.status
                or current["revision"] != record.revision
            ):
                upserts.append(self._index_row(record, path, digest))
        deletes = []
        for record_id, row in rows.items():
            if record_id in seen or record_id in malformed:
                continue
            stored = self.root / row["vault_relpath"]
            if stored.exists():
                try:
                    self._parse_path(project_id, stored, stored.read_bytes())
                except StorageError:
                    continue
            deletes.append(record_id)
        if upserts or deletes:
            self.index.update_memory_rows(upserts, deletes)

    def _parse_path(self, project_id: str, path: Path, raw: bytes):
        resolve_inside(self.root, path)
        try:
            data = yaml.safe_load(raw)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("MALFORMED", "YAML could not be parsed.") from exc
        if not isinstance(data, dict):
            raise StorageError("MALFORMED", "YAML root must be a mapping.")
        try:
            record = parse_record(data)
        except ValidationError as exc:
            raise StorageError("MALFORMED", "Memory file failed schema validation.") from exc
        if record.project_id != project_id:
            raise StorageError("MALFORMED", "Memory file is for a different project.")
        check_record_id(record.type, record.id)
        if record.type == "status":
            if path.name != "status.yaml" or record.id != status_record_id(project_id):
                raise StorageError("MALFORMED", "Status file does not match the project.")
        elif path.name != f"{record.id}.yaml":
            raise StorageError("MALFORMED", "Memory filename does not match its id.")
        return record

    def _try_load(self, path: Path, project_id: str):
        if not path.exists() or path.is_symlink():
            return None
        try:
            return self._parse_path(project_id, path, path.read_bytes())
        except StorageError:
            return None

    def _load_type(self, directory: Path, project_id: str, record_type: str) -> list:
        folder = directory / TYPE_DIRS[record_type]
        if not folder.exists():
            return []
        records = []
        for path in sorted(folder.glob("*.yaml")):
            loaded = self._try_load(path, project_id)
            if loaded is not None and loaded.type == record_type:
                records.append(loaded)
        return records

    def _iter_record_files(self, directory: Path):
        status = directory / "status.yaml"
        if status.exists():
            yield status
        for folder_name in TYPE_DIRS.values():
            folder = directory / folder_name
            if folder.exists():
                yield from sorted(folder.glob("*.yaml"))

    def _index_row(self, record, path: Path, digest: str) -> dict:
        topic = getattr(record, "topic", None) or getattr(record, "title", None)
        return {
            "id": record.id,
            "project_id": record.project_id,
            "type": record.type,
            "status": record.status,
            "topic": topic,
            "revision": record.revision,
            "content_hash": digest,
            "vault_relpath": path.resolve().relative_to(self.root).as_posix(),
            "updated_at": record.updated_at,
        }

    def _record_path(self, directory: Path, record) -> Path:
        if record.type == "status":
            return resolve_inside(self.root, directory / "status.yaml")
        return resolve_inside(self.root, directory / TYPE_DIRS[record.type] / f"{record.id}.yaml")

    def _path_for_id(self, directory: Path, project_id: str, record_id: str) -> Path:
        if record_id == status_record_id(project_id):
            return resolve_inside(self.root, directory / "status.yaml")
        prefix = record_id.split("_", 1)[0]
        kind = self._prefixes.get(prefix)
        if kind is None or kind not in TYPE_DIRS:
            raise StorageError("VALIDATION", "Record id is not valid.")
        check_record_id(kind, record_id)
        return resolve_inside(self.root, directory / TYPE_DIRS[kind] / f"{record_id}.yaml")

    def _project_dir(self, project_id: str) -> Path:
        return resolve_inside(self.root, self.root / "memory" / "projects" / project_id)

    def _require_project(self, project_id: str) -> Path:
        directory = self._project_dir(check_project_id(project_id))
        if not (directory / "project.yaml").exists():
            raise StorageError("NOT_FOUND", "Project was not found.")
        return directory
