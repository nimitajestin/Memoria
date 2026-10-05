"""Close the index and open it again, as a process restart would."""

from core.storage.memory_repo import MemoryRepository


def test_memory_survives_reopen(tmp_path) -> None:
    store = MemoryRepository(tmp_path)
    store.create_project("project_harbor", "Harbor")
    record = store.create_record(
        "project_harbor",
        {
            "type": "fact",
            "topic": "hardware",
            "statement": "The machine has 8 GB of RAM.",
            "source": {"kind": "user", "ref": None, "quote": None},
        },
    )
    store.close()
    reopened = MemoryRepository(tmp_path)
    loaded = reopened.get_record("project_harbor", record.id)
    assert loaded.statement == "The machine has 8 GB of RAM."
    reopened.close()
