"""Pydantic models for project memory. Field order is the canonical YAML order."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from core.safety import EXECUTION_ID_RE, PROJECT_ID_RE, REF_RE

MAX_BODY = 8000
MAX_TOPIC = 200
MAX_QUOTE = 240


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
            return text
        if text.endswith("+00:00"):
            parsed = datetime.fromisoformat(text)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError("timestamp must be ISO-8601 UTC")


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(MemoryModel):
    kind: Literal["user", "document", "conversation", "agent", "import"] = "user"
    ref: str | None = None
    quote: str | None = None

    @model_validator(mode="after")
    def check_ref(self) -> Source:
        if self.quote is not None and len(self.quote) > MAX_QUOTE:
            raise ValueError("quote exceeds 240 characters")
        if self.ref is not None and REF_RE.fullmatch(self.ref) is None:
            raise ValueError("source ref is not a valid id")
        return self


class RecordBase(MemoryModel):
    id: str
    type: str
    project_id: str
    created_at: str
    updated_at: str
    status: Literal["active", "superseded", "withdrawn"]
    revision: int = Field(ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Source = Field(default_factory=Source)
    supersedes: str | None = None
    conflicts_with: list[str] = Field(default_factory=list)
    created_by: Literal["user", "agent", "import"] = "user"
    execution_id: str | None = None

    @model_validator(mode="after")
    def check_common(self) -> RecordBase:
        if PROJECT_ID_RE.fullmatch(self.project_id) is None:
            raise ValueError("invalid project id")
        self.created_at = _timestamp(self.created_at)
        self.updated_at = _timestamp(self.updated_at)
        if self.confidence is not None:
            self.confidence = round(float(self.confidence), 4)
        if self.execution_id is not None and EXECUTION_ID_RE.fullmatch(self.execution_id) is None:
            raise ValueError("invalid execution id")
        if self.supersedes is not None and REF_RE.fullmatch(self.supersedes) is None:
            raise ValueError("invalid supersedes id")
        for item in self.conflicts_with:
            if REF_RE.fullmatch(item) is None:
                raise ValueError("invalid conflict id")
        return self


class FactRecord(RecordBase):
    type: Literal["fact"] = "fact"
    topic: str = Field(min_length=1, max_length=MAX_TOPIC)
    statement: str = Field(min_length=1, max_length=MAX_BODY)


class DecisionRecord(RecordBase):
    type: Literal["decision"] = "decision"
    topic: str = Field(min_length=1, max_length=MAX_TOPIC)
    decision: str = Field(min_length=1, max_length=MAX_BODY)
    reason: str = Field(min_length=1, max_length=MAX_BODY)


class GoalRecord(RecordBase):
    type: Literal["goal"] = "goal"
    statement: str = Field(min_length=1, max_length=MAX_BODY)
    goal_status: Literal["open", "done", "dropped"]


class KnowledgeRecord(RecordBase):
    type: Literal["knowledge"] = "knowledge"
    title: str = Field(min_length=1, max_length=MAX_TOPIC)
    body: str = Field(min_length=1, max_length=MAX_BODY)
    tags: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def check_tags(self) -> KnowledgeRecord:
        for tag in self.tags:
            if not isinstance(tag, str) or not 1 <= len(tag) <= 40:
                raise ValueError("invalid tag")
        return self


class EpisodeRecord(RecordBase):
    type: Literal["episode"] = "episode"
    occurred_at: str
    summary: str = Field(min_length=1, max_length=MAX_BODY)

    @model_validator(mode="after")
    def check_occurred(self) -> EpisodeRecord:
        self.occurred_at = _timestamp(self.occurred_at)
        return self


class SummaryRecord(RecordBase):
    type: Literal["conversation_summary"] = "conversation_summary"
    conversation_id: str
    summary: str = Field(min_length=1, max_length=MAX_BODY)

    @model_validator(mode="after")
    def check_conversation(self) -> SummaryRecord:
        if re.fullmatch(r"^conv_[0-9a-f]{12}$", self.conversation_id) is None:
            raise ValueError("invalid conversation id")
        return self


class StatusRecord(RecordBase):
    type: Literal["status"] = "status"
    phase: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=MAX_BODY)
    blockers: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def check_blockers(self) -> StatusRecord:
        for item in self.blockers:
            if not isinstance(item, str) or not 1 <= len(item) <= 200:
                raise ValueError("invalid blocker")
        return self


Record = Annotated[
    FactRecord
    | DecisionRecord
    | GoalRecord
    | KnowledgeRecord
    | EpisodeRecord
    | SummaryRecord
    | StatusRecord,
    Field(discriminator="type"),
]

RECORD_ADAPTER = TypeAdapter(Record)


class ProjectFile(MemoryModel):
    id: str
    name: str = Field(min_length=1, max_length=MAX_TOPIC)
    description: str = Field(default="", max_length=4000)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def check_project(self) -> ProjectFile:
        if PROJECT_ID_RE.fullmatch(self.id) is None:
            raise ValueError("invalid project id")
        self.created_at = _timestamp(self.created_at)
        self.updated_at = _timestamp(self.updated_at)
        return self


class DraftBase(MemoryModel):
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Source = Field(default_factory=Source)
    supersedes: str | None = None
    conflicts_with: list[str] = Field(default_factory=list)
    created_by: Literal["user", "agent", "import"] = "user"
    execution_id: str | None = None
    project_id: str | None = None

    @model_validator(mode="after")
    def check_draft(self) -> DraftBase:
        if self.confidence is not None:
            self.confidence = round(float(self.confidence), 4)
        if self.project_id is not None and PROJECT_ID_RE.fullmatch(self.project_id) is None:
            raise ValueError("invalid project id")
        if self.execution_id is not None and EXECUTION_ID_RE.fullmatch(self.execution_id) is None:
            raise ValueError("invalid execution id")
        if self.supersedes is not None and REF_RE.fullmatch(self.supersedes) is None:
            raise ValueError("invalid supersedes id")
        for item in self.conflicts_with:
            if REF_RE.fullmatch(item) is None:
                raise ValueError("invalid conflict id")
        return self


class FactDraft(DraftBase):
    type: Literal["fact"] = "fact"
    topic: str = Field(min_length=1, max_length=MAX_TOPIC)
    statement: str = Field(min_length=1, max_length=MAX_BODY)


class DecisionDraft(DraftBase):
    type: Literal["decision"] = "decision"
    topic: str = Field(min_length=1, max_length=MAX_TOPIC)
    decision: str = Field(min_length=1, max_length=MAX_BODY)
    reason: str = Field(min_length=1, max_length=MAX_BODY)


class GoalDraft(DraftBase):
    type: Literal["goal"] = "goal"
    statement: str = Field(min_length=1, max_length=MAX_BODY)
    goal_status: Literal["open", "done", "dropped"] = "open"


class KnowledgeDraft(DraftBase):
    type: Literal["knowledge"] = "knowledge"
    title: str = Field(min_length=1, max_length=MAX_TOPIC)
    body: str = Field(min_length=1, max_length=MAX_BODY)
    tags: list[str] = Field(default_factory=list, max_length=16)


class EpisodeDraft(DraftBase):
    type: Literal["episode"] = "episode"
    occurred_at: str
    summary: str = Field(min_length=1, max_length=MAX_BODY)

    @model_validator(mode="after")
    def check_occurred(self) -> EpisodeDraft:
        self.occurred_at = _timestamp(self.occurred_at)
        return self


class SummaryDraft(DraftBase):
    type: Literal["conversation_summary"] = "conversation_summary"
    conversation_id: str
    summary: str = Field(min_length=1, max_length=MAX_BODY)

    @model_validator(mode="after")
    def check_conversation(self) -> SummaryDraft:
        if re.fullmatch(r"^conv_[0-9a-f]{12}$", self.conversation_id) is None:
            raise ValueError("invalid conversation id")
        return self


Draft = Annotated[
    FactDraft | DecisionDraft | GoalDraft | KnowledgeDraft | EpisodeDraft | SummaryDraft,
    Field(discriminator="type"),
]

DRAFT_ADAPTER = TypeAdapter(Draft)

MUTABLE_FIELDS = {
    "fact": {"topic", "statement", "confidence", "source", "conflicts_with"},
    "decision": {"confidence", "source", "status"},
    "goal": {"statement", "goal_status", "confidence", "source"},
    "knowledge": {"title", "body", "tags", "confidence", "source"},
    "episode": {"summary", "occurred_at", "confidence", "source"},
    "conversation_summary": {"summary", "conversation_id", "confidence", "source"},
    "status": {"phase", "summary", "blockers", "status"},
}


class MemoryHit(MemoryModel):
    id: str
    type: str
    title_or_topic: str
    score: float
    snippet: str
    updated_at: str


def parse_record(data: dict) -> FactRecord | DecisionRecord | GoalRecord | KnowledgeRecord | EpisodeRecord | SummaryRecord | StatusRecord:
    return RECORD_ADAPTER.validate_python(data)
