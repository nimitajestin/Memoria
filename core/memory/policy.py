"""Deterministic memory policy. This module does not write files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.memory.content import fingerprint, normalize_text
from core.safety import ACTIVE_CAPS, REF_RE

Outcome = Literal["reject", "update", "create"]
Reason = Literal[
    "low_confidence",
    "not_durable",
    "unsupported",
    "duplicate",
    "conflict",
    "capacity",
    "revision_mismatch",
    "accepted",
]

CONFIDENCE_FLOOR = 0.6


@dataclass(frozen=True)
class PolicyRecord:
    id: str
    type: str
    topic: str | None
    content_hash: str
    identity_hash: str
    revision: int
    status: str


class PolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Outcome
    reason: Reason
    target_id: str | None = None
    conflict_ids: list[str] = Field(default_factory=list)
    detail: str = ""


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "fact",
        "decision",
        "goal",
        "knowledge",
        "episode",
        "conversation_summary",
        "status",
    ]
    confidence: float = Field(ge=0, le=1)
    stable: bool
    project_specific: bool
    future_useful: bool
    evidence_refs: list[str] = Field(default_factory=list, max_length=8)
    source_kind: Literal["user", "document", "conversation", "agent", "import"] = "user"
    topic: str | None = None
    statement: str | None = None
    decision: str | None = None
    reason: str | None = None
    title: str | None = None
    body: str | None = None
    tags: list[str] = Field(default_factory=list)
    goal_status: Literal["open", "done", "dropped"] | None = None
    summary: str | None = None
    occurred_at: str | None = None
    conversation_id: str | None = None
    phase: str | None = None
    blockers: list[str] = Field(default_factory=list)
    supersedes: str | None = None

    @model_validator(mode="after")
    def check_fields(self) -> MemoryCandidate:
        required = {
            "fact": ("topic", "statement"),
            "decision": ("topic", "decision", "reason"),
            "goal": ("statement", "goal_status"),
            "knowledge": ("title", "body"),
            "episode": ("summary", "occurred_at"),
            "conversation_summary": ("summary", "conversation_id"),
            "status": ("phase", "summary"),
        }[self.type]
        for name in required:
            if not getattr(self, name):
                raise ValueError(f"{self.type} requires {name}")
        for ref in self.evidence_refs:
            if REF_RE.fullmatch(ref) is None:
                raise ValueError("invalid evidence ref")
        if self.supersedes is not None and REF_RE.fullmatch(self.supersedes) is None:
            raise ValueError("invalid supersedes id")
        return self


def _reject(reason: Reason, detail: str, target_id: str | None = None, conflict_ids: list[str] | None = None) -> PolicyResult:
    return PolicyResult(
        outcome="reject",
        reason=reason,
        target_id=target_id,
        conflict_ids=conflict_ids or [],
        detail=detail,
    )


def structural_disposition(
    *,
    record_type: str,
    topic: str | None,
    content_digest: str,
    identity_digest: str,
    supersedes: str | None,
    existing: list[PolicyRecord],
    cap: int,
    expected_revision: int | None = None,
) -> PolicyResult:
    """Duplicate, conflict, capacity, and in-place update rules shared by the vault."""

    active = [item for item in existing if item.status == "active" and item.type == record_type]
    duplicate = next((item for item in active if item.content_hash == content_digest), None)
    if duplicate is not None:
        return _reject("duplicate", "An active record already has this content.", duplicate.id)

    if record_type == "status":
        current = next((item for item in existing if item.type == "status"), None)
        if current is None:
            if len(active) >= cap:
                return _reject("capacity", "The active status cap is full.")
            return PolicyResult(outcome="create", reason="accepted")
        if expected_revision != current.revision:
            return _reject(
                "revision_mismatch",
                "Status update requires the current revision.",
                current.id,
            )
        return PolicyResult(outcome="update", reason="accepted", target_id=current.id)

    if record_type == "goal":
        current = next((item for item in active if item.identity_hash == identity_digest), None)
        if current is not None:
            if expected_revision != current.revision:
                return _reject(
                    "revision_mismatch",
                    "Goal update requires the current revision.",
                    current.id,
                )
            return PolicyResult(outcome="update", reason="accepted", target_id=current.id)

    if record_type == "decision" and supersedes:
        target = next((item for item in active if item.id == supersedes), None)
        if target is None:
            return _reject("conflict", "supersedes does not name an active decision.")
        others = [
            item.id
            for item in active
            if item.id != target.id and item.topic and topic and normalize_text(item.topic) == normalize_text(topic)
        ]
        return PolicyResult(
            outcome="create",
            reason="accepted",
            target_id=target.id,
            conflict_ids=others,
        )

    if topic:
        clashes = [
            item
            for item in active
            if item.topic and normalize_text(item.topic) == normalize_text(topic)
        ]
        if clashes:
            ids = [item.id for item in clashes]
            if record_type == "decision":
                return _reject(
                    "conflict",
                    "An active decision already covers this topic. Create a revision with supersedes.",
                    conflict_ids=ids,
                )
            if len(active) >= cap:
                return _reject("capacity", "The active record cap is full.", conflict_ids=ids)
            return PolicyResult(
                outcome="create",
                reason="conflict",
                conflict_ids=ids,
                detail="The new record conflicts with an existing topic.",
            )

    if len(active) >= cap:
        return _reject("capacity", "The active record cap is full.")
    return PolicyResult(outcome="create", reason="accepted")


def evaluate(
    candidate: MemoryCandidate | dict,
    existing: list[PolicyRecord],
    *,
    caps: dict[str, int] | None = None,
    expected_revision: int | None = None,
) -> PolicyResult:
    """Apply the agent gates, then the structural rules. Nothing is written."""

    if not isinstance(candidate, MemoryCandidate):
        try:
            candidate = MemoryCandidate.model_validate(candidate)
        except ValidationError:
            return _reject("unsupported", "Candidate failed schema validation.")
    if candidate.confidence < CONFIDENCE_FLOOR:
        return _reject("low_confidence", "Confidence is below 0.6.")
    if not (candidate.stable and candidate.project_specific and candidate.future_useful):
        return _reject("not_durable", "The candidate is not stable, project-specific, and future-useful.")
    needs_evidence = candidate.type in {"fact", "decision"}
    if needs_evidence and candidate.source_kind != "user" and not candidate.evidence_refs:
        return _reject("unsupported", "Facts and decisions need evidence or an explicit user statement.")

    digest, identity, topic = fingerprint(candidate.type, candidate.model_dump())
    limit = (caps or ACTIVE_CAPS)[candidate.type]
    return structural_disposition(
        record_type=candidate.type,
        topic=topic,
        content_digest=digest,
        identity_digest=identity,
        supersedes=candidate.supersedes,
        existing=existing,
        cap=limit,
        expected_revision=expected_revision,
    )
