"""Load the Harbor corpus into an empty vault. No MCP, embeddings, or UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.memory.content import sha256_bytes
from core.schemas.conversations import ConversationFile, Turn
from core.schemas.documents import DocumentMeta
from core.schemas.memory import Source
from core.storage.conversations import ConversationStore
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from core.storage.vault import atomic_write

CONTROLLED_ROOT = Path(__file__).resolve().parent
HARBOR = "project_harbor"
DECOY = "project_decoy"
CREATED = "2026-01-15T12:00:00Z"
UPDATED = "2026-03-01T12:00:00Z"

Category = Literal[
    "direct_retrieval",
    "cross_document",
    "memory_recall",
    "temporal",
    "conflict",
    "irrelevant_rejection",
    "multi_turn",
    "cross_session",
    "import_recall",
]


class PriorTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    category: Category
    session: Literal["single", "cross"]
    question: str
    prior_turns: list[PriorTurn] = Field(default_factory=list)
    expects_route: Literal["none", "memory", "documents", "both"]
    gold_memory_ids: list[str] = Field(default_factory=list)
    gold_document_ids: list[str] = Field(default_factory=list)
    gold_markers: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    gold_conversation_ids: list[str] = Field(default_factory=list)
    required_points: list[str]

    @model_validator(mode="before")
    @classmethod
    def stringify_points(cls, data):
        if not isinstance(data, dict):
            return data
        for key in ("required_points", "forbidden_points"):
            values = data.get(key)
            if isinstance(values, list):
                data[key] = [str(item) for item in values]
        return data
    forbidden_points: list[str] = Field(default_factory=list)
    acceptable_grounding: list[str]


class HarborLoadResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    catalog: dict
    questions: list[Question]
    document_ids: list[str]
    memory_ids: dict[str, str]


def load_catalog(root: Path = CONTROLLED_ROOT) -> dict:
    payload = yaml.safe_load((root / "catalog.yaml").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog.yaml must be a mapping")
    return payload


def load_questions(root: Path = CONTROLLED_ROOT) -> list[Question]:
    payload = yaml.safe_load((root / "questions.yaml").read_text(encoding="utf-8"))
    items = payload["questions"]
    return [Question.model_validate(item) for item in items]


def load_not_durable_candidate(root: Path = CONTROLLED_ROOT) -> dict:
    payload = yaml.safe_load((root / "not_durable_candidate.yaml").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("not_durable_candidate.yaml must be a mapping")
    return payload


def parse_labeled_transcript(text: str) -> list[Turn]:
    turns: list[Turn] = []
    role: str | None = None
    lines: list[str] = []

    def flush() -> None:
        nonlocal role, lines
        if role is None:
            return
        content = "\n".join(lines).strip()
        if content:
            turns.append(Turn(role=role, content=content, timestamp=None))
        role = None
        lines = []

    for line in text.splitlines():
        if line.startswith("User:"):
            flush()
            role = "user"
            lines = [line[len("User:") :].strip()]
        elif line.startswith("Assistant:"):
            flush()
            role = "assistant"
            lines = [line[len("Assistant:") :].strip()]
        elif role is not None:
            lines.append(line)
    flush()
    if not turns:
        raise ValueError("transcript contained no User/Assistant turns")
    return turns


def _user_source() -> dict:
    return Source(kind="user", ref=None, quote=None).model_dump(mode="json")


def _harbor_records() -> list[dict]:
    user = _user_source()
    return [
        {
            "id": "decision_01d000000002",
            "type": "decision",
            "project_id": HARBOR,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "superseded",
            "revision": 2,
            "confidence": 0.7,
            "source": user,
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "topic": "vector_storage",
            "decision": "Use Qdrant as the Harbor retrieval store.",
            "reason": "An early draft assumed a vector database service would be needed.",
        },
        {
            "id": "decision_a11ce0000001",
            "type": "decision",
            "project_id": HARBOR,
            "created_at": UPDATED,
            "updated_at": UPDATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.95,
            "source": user,
            "supersedes": "decision_01d000000002",
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "topic": "vector_storage",
            "decision": "Use exact cosine search over float32 vectors stored in SQLite.",
            "reason": "The Harbor machine has 8 GB of RAM and the evaluation corpus is small.",
        },
        {
            "id": "fact_8ba000000001",
            "type": "fact",
            "project_id": HARBOR,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "active",
            "revision": 1,
            "confidence": 1.0,
            "source": user,
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "topic": "hardware",
            "statement": "The Harbor workstation has 8 GB of RAM and no discrete GPU.",
        },
        {
            "id": "fact_c0f11c000001",
            "type": "fact",
            "project_id": HARBOR,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.7,
            "source": user,
            "supersedes": None,
            "conflicts_with": ["fact_c0f11c000002"],
            "created_by": "user",
            "execution_id": None,
            "topic": "standup",
            "statement": "The Harbor standup is at 10:00 UTC.",
        },
        {
            "id": "fact_c0f11c000002",
            "type": "fact",
            "project_id": HARBOR,
            "created_at": UPDATED,
            "updated_at": UPDATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.7,
            "source": user,
            "supersedes": None,
            "conflicts_with": ["fact_c0f11c000001"],
            "created_by": "user",
            "execution_id": None,
            "topic": "standup",
            "statement": "The Harbor standup is at 14:00 UTC.",
        },
        {
            "id": "knowledge_aa0000000001",
            "type": "knowledge",
            "project_id": HARBOR,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.8,
            "source": user,
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "title": "Logo color",
            "body": "The Harbor project logo is described as blue in an informal note.",
            "tags": ["visual"],
        },
        {
            "id": "goal_aa0000000001",
            "type": "goal",
            "project_id": HARBOR,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "active",
            "revision": 1,
            "confidence": 1.0,
            "source": user,
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "statement": "Compare three systems: stateless RAG, persistent memory without MCP, and persistent memory through MCP.",
            "goal_status": "open",
        },
        {
            "id": "episode_aa0000000001",
            "type": "episode",
            "project_id": HARBOR,
            "created_at": UPDATED,
            "updated_at": UPDATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.9,
            "source": user,
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "occurred_at": UPDATED,
            "summary": "The architecture freeze selected SQLite exact search because of the 8 GB RAM constraint.",
        },
    ]


def _original_name(filename: str) -> str:
    suffix = Path(filename).suffix
    if suffix == ".md":
        return "original.md"
    if suffix == ".txt":
        return "original.txt"
    if suffix == ".py":
        return "original.py"
    return f"original{suffix}"


def load_harbor(data_root: Path, root: Path = CONTROLLED_ROOT) -> HarborLoadResult:
    catalog = load_catalog(root)
    questions = load_questions(root)
    memory = MemoryRepository(data_root)
    documents = DocumentRepository(data_root, memory.index)
    conversations = ConversationStore(data_root)

    memory.create_project(HARBOR, "Harbor", "Controlled evaluation project.")
    memory.create_project(DECOY, "Decoy", "Second project used to test boundaries.")
    status = memory.get_record(HARBOR, "status_project_harbor")
    memory.update_record(
        HARBOR,
        status.id,
        {
            "phase": "evaluation-dataset",
            "summary": "Harbor controlled corpus is seeded.",
            "blockers": [],
        },
        status.revision,
    )

    pending_conflicts: dict[str, list[str]] = {}
    for record in _harbor_records():
        conflicts = list(record.get("conflicts_with") or [])
        if conflicts:
            pending_conflicts[record["id"]] = conflicts
            record = {**record, "conflicts_with": []}
        memory.seed_record(record)
    for record_id, others in pending_conflicts.items():
        current = memory.get_record(HARBOR, record_id)
        memory.update_record(
            HARBOR,
            record_id,
            {"conflicts_with": others},
            current.revision,
        )

    memory.seed_record(
        {
            "id": "fact_deca00000001",
            "type": "fact",
            "project_id": DECOY,
            "created_at": CREATED,
            "updated_at": CREATED,
            "status": "active",
            "revision": 1,
            "confidence": 0.9,
            "source": _user_source(),
            "supersedes": None,
            "conflicts_with": [],
            "created_by": "user",
            "execution_id": None,
            "topic": "retrieval",
            "statement": "Harbor retrieval uses Redis.",
        }
    )

    document_ids: list[str] = []
    for item in catalog["documents"]:
        source = root / "documents" / item["filename"]
        data = source.read_bytes()
        document_id = item["id"]
        directory = Path(data_root).resolve() / "documents" / HARBOR / document_id
        atomic_write(directory / _original_name(item["filename"]), data)
        documents.add(
            DocumentMeta(
                id=document_id,
                project_id=HARBOR,
                filename=item["filename"],
                file_type=item["file_type"],
                byte_size=len(data),
                content_hash=sha256_bytes(data),
                indexed_at=None,
                status="pending",
                error=None,
                chunk_count=0,
                vault_relpath=f"documents/{HARBOR}/{document_id}",
            )
        )
        document_ids.append(document_id)

    titles = {
        "conv_aa0000000001": "Planning chat",
        "conv_aa0000000002": "Aside chat",
    }
    formats = {
        "planning.md": "markdown",
        "aside.txt": "txt",
    }
    for item in catalog["conversations"]:
        filename = item["filename"]
        text = (root / "conversations" / filename).read_text(encoding="utf-8")
        conversations.save(
            ConversationFile(
                id=item["id"],
                project_id=HARBOR,
                source="import",
                origin_format=formats[filename],
                created_at=CREATED,
                title=titles[item["id"]],
                turns=parse_labeled_transcript(text),
            )
        )

    loaded = HarborLoadResult(
        catalog=catalog,
        questions=questions,
        document_ids=document_ids,
        memory_ids=catalog["memory_ids"],
    )
    documents.close()
    memory.close()
    return loaded


@dataclass(frozen=True)
class HarborPaths:
    root: Path = CONTROLLED_ROOT
