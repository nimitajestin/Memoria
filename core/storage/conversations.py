"""Read and write normalized conversation files."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from core.errors import StorageError
from core.safety import FileLock, check_project_id, resolve_inside
from core.schemas.conversations import ConversationFile
from core.schemas.memory import utc_now
from core.storage.vault import atomic_write, canonical_json, read_json


class ConversationStore:
    def __init__(self, data_root: Path) -> None:
        self.root = Path(data_root).resolve()

    def path_for(self, project_id: str, conversation_id: str) -> Path:
        project_id = check_project_id(project_id)
        directory = self.root / "conversations" / project_id
        return resolve_inside(self.root, directory / f"{conversation_id}.json")

    def save(self, conversation: ConversationFile) -> ConversationFile:
        path = self.path_for(conversation.project_id, conversation.id)
        lock_path = self.root / "conversations" / conversation.project_id / ".lock"
        with FileLock(lock_path):
            atomic_write(path, canonical_json(conversation))
        return conversation

    def load(self, project_id: str, conversation_id: str) -> ConversationFile:
        path = self.path_for(project_id, conversation_id)
        if not path.exists():
            raise StorageError("NOT_FOUND", "Conversation file was not found.")
        try:
            return ConversationFile.model_validate(read_json(path))
        except ValidationError as exc:
            raise StorageError("MALFORMED", "Conversation file failed schema validation.") from exc
        except StorageError:
            raise

    def turn_texts(self, project_id: str, conversation_id: str) -> list[str] | None:
        path = self.path_for(project_id, conversation_id)
        if not path.exists():
            return None
        conversation = self.load(project_id, conversation_id)
        if conversation.project_id != project_id:
            return None
        return [turn.content for turn in conversation.turns]

    @staticmethod
    def new_timestamp() -> str:
        return utc_now()
