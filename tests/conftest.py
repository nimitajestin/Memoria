from pathlib import Path

import pytest

from core.errors import StorageError
from core.storage.memory_repo import MemoryRepository


@pytest.fixture
def repo(tmp_path: Path):
    store = MemoryRepository(tmp_path)
    yield store
    store.close()


def fact_payload(**overrides) -> dict:
    payload = {
        "type": "fact",
        "topic": "hardware",
        "statement": "The machine has 8 GB of RAM.",
        "source": {"kind": "user", "ref": None, "quote": None},
        "created_by": "user",
    }
    payload.update(overrides)
    return payload
