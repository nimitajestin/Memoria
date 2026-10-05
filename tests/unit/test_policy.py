from core.memory.content import fingerprint
from core.memory.policy import PolicyRecord, evaluate


def candidate(**overrides) -> dict:
    payload = {
        "type": "fact",
        "confidence": 0.8,
        "stable": True,
        "project_specific": True,
        "future_useful": True,
        "evidence_refs": [],
        "source_kind": "user",
        "topic": "hardware",
        "statement": "The machine has 8 GB of RAM.",
    }
    payload.update(overrides)
    return payload


def test_low_confidence_and_boundary() -> None:
    assert evaluate(candidate(confidence=0.59), []).reason == "low_confidence"
    assert evaluate(candidate(confidence=0.6), []).outcome == "create"


def test_not_durable_and_unsupported() -> None:
    assert evaluate(candidate(future_useful=False), []).reason == "not_durable"
    rejected = evaluate(candidate(source_kind="document"), [])
    assert rejected.reason == "unsupported"
    accepted = evaluate(
        candidate(source_kind="document", evidence_refs=["chunk_0123456789ab"]),
        [],
    )
    assert accepted.outcome == "create"


def test_duplicate_content_is_rejected() -> None:
    digest, identity, topic = fingerprint(
        "fact",
        {"topic": "other", "statement": "The machine has 8 GB of RAM."},
    )
    existing = [PolicyRecord("fact_0123456789ab", "fact", "other", digest, identity, 1, "active")]
    result = evaluate(candidate(topic="hardware"), existing)
    assert result.outcome == "reject"
    assert result.reason == "duplicate"
    assert result.target_id == "fact_0123456789ab"


def test_decision_topic_conflict_does_not_authorize_overwrite() -> None:
    digest, identity, _topic = fingerprint(
        "decision",
        {"topic": "vector_storage", "decision": "Use SQLite.", "reason": "The machine has 8 GB of RAM."},
    )
    existing = [
        PolicyRecord("decision_0123456789ab", "decision", "vector_storage", digest, identity, 1, "active")
    ]
    result = evaluate(
        {
            "type": "decision",
            "confidence": 0.9,
            "stable": True,
            "project_specific": True,
            "future_useful": True,
            "source_kind": "user",
            "topic": "vector_storage",
            "decision": "Use a vector server.",
            "reason": "A different reason.",
        },
        existing,
    )
    assert result.outcome == "reject"
    assert result.reason == "conflict"


def test_fact_topic_conflict_keeps_both() -> None:
    digest, identity, _topic = fingerprint(
        "fact",
        {"topic": "hardware", "statement": "The machine has 16 GB of RAM."},
    )
    existing = [PolicyRecord("fact_0123456789ab", "fact", "hardware", digest, identity, 1, "active")]
    result = evaluate(candidate(), existing)
    assert result.outcome == "create"
    assert result.reason == "conflict"
    assert result.conflict_ids == ["fact_0123456789ab"]


def test_capacity_cap() -> None:
    existing = [
        PolicyRecord(f"fact_{index:012x}", "fact", f"topic-{index}", f"hash-{index}", f"hash-{index}", 1, "active")
        for index in range(2)
    ]
    result = evaluate(candidate(), existing, caps={"fact": 2})
    assert result.outcome == "reject"
    assert result.reason == "capacity"


def test_goal_update_requires_revision() -> None:
    _digest, identity, _topic = fingerprint(
        "goal",
        {"statement": "Ship the evaluation.", "goal_status": "open"},
    )
    digest, _identity, _topic = fingerprint(
        "goal",
        {"statement": "Ship the evaluation.", "goal_status": "open"},
    )
    existing = [PolicyRecord("goal_0123456789ab", "goal", None, digest, identity, 3, "active")]
    proposal = {
        "type": "goal",
        "confidence": 0.9,
        "stable": True,
        "project_specific": True,
        "future_useful": True,
        "source_kind": "user",
        "statement": "Ship the evaluation.",
        "goal_status": "done",
    }
    mismatch = evaluate(proposal, existing, expected_revision=1)
    assert mismatch.reason == "revision_mismatch"
    matched = evaluate(proposal, existing, expected_revision=3)
    assert matched.outcome == "update"
    assert matched.target_id == "goal_0123456789ab"
