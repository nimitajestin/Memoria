import pytest
from pydantic import ValidationError

from core.errors import StorageError
from core.safety import check_project_id
from core.schemas.memory import FactRecord, Source
from core.storage.vault import canonical_bytes


def _fact() -> FactRecord:
    return FactRecord(
        id="fact_0123456789ab",
        type="fact",
        project_id="project_harbor",
        created_at="2026-10-05T00:00:00Z",
        updated_at="2026-10-05T00:00:00Z",
        status="active",
        revision=1,
        topic="hardware",
        statement="Note: keep the index local.",
        source=Source(),
        created_by="user",
    )


def test_canonical_yaml_is_stable_and_uses_lf() -> None:
    record = _fact()
    first = canonical_bytes(record)
    second = canonical_bytes(record)
    assert first == second
    assert b"\r\n" not in first
    loaded = FactRecord.model_validate(__import__("yaml").safe_load(first))
    assert canonical_bytes(loaded) == first


def test_quote_limit_and_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Source(quote="x" * 241)
    with pytest.raises(ValidationError):
        FactRecord.model_validate({**_fact().model_dump(mode="json"), "extra": "no"})


def test_project_id_rejects_traversal() -> None:
    with pytest.raises(StorageError) as caught:
        check_project_id("../other")
    assert caught.value.code == "FORBIDDEN"
    with pytest.raises(StorageError) as caught:
        check_project_id("Bad ID")
    assert caught.value.code == "VALIDATION"
    assert check_project_id("project_harbor") == "project_harbor"
