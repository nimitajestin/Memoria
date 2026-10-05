import json
from pathlib import Path

from core.errors import StorageError
from core.memory.policy import evaluate
from core.storage.memory_repo import MemoryRepository
from evaluation.datasets.controlled.load import CONTROLLED_ROOT, load_not_durable_candidate
from ingestion.importing.candidates import extract_candidates
from ingestion.importing.parse import parse_transcript


def test_not_durable_aside_is_rejected() -> None:
    result = evaluate(load_not_durable_candidate(), [])
    assert result.outcome == "reject"
    assert result.reason == "not_durable"


def test_import_markdown_writes_transcript_and_durable_fact(tmp_path: Path) -> None:
    memory = MemoryRepository(tmp_path)
    memory.create_project("project_harbor", "Harbor")
    report = memory.import_conversation(
        "project_harbor",
        CONTROLLED_ROOT / "conversations" / "planning.md",
        title="Planning chat",
    )
    conv_id = report["conversation"]["id"]
    path = tmp_path / "conversations" / "project_harbor" / f"{conv_id}.json"
    assert path.exists()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["origin_format"] == "markdown"
    assert any("Ollama" in item["statement"] for item in report["accepted"])
    assert any(item["reason"] == "not_durable" for item in report["rejected"])
    facts = list((tmp_path / "memory" / "projects" / "project_harbor" / "facts").glob("*.yaml"))
    joined = "\n".join(path.read_text(encoding="utf-8") for path in facts)
    assert "host" in joined.casefold()
    assert "pizza" not in joined.casefold()
    memory.close()


def test_import_txt_and_json_and_refuse_bad_files(tmp_path: Path) -> None:
    memory = MemoryRepository(tmp_path)
    memory.create_project("project_harbor", "Harbor")
    txt = memory.import_conversation("project_harbor", CONTROLLED_ROOT / "conversations" / "aside.txt")
    assert txt["rejected"]
    assert "cat" in " ".join(item["statement"] for item in txt["rejected"]).casefold()
    json_path = tmp_path / "chat.json"
    json_path.write_text(
        json.dumps([{"role": "user", "content": "Keep the Harbor MCP server on port 8765."}]),
        encoding="utf-8",
    )
    js = memory.import_conversation("project_harbor", json_path)
    assert js["accepted"]
    bad = tmp_path / "nope.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    before = list((tmp_path / "conversations" / "project_harbor").glob("*.json"))
    try:
        memory.import_conversation("project_harbor", bad)
        raised = False
    except StorageError as exc:
        raised = True
        assert exc.code == "UNSUPPORTED"
    assert raised
    after = list((tmp_path / "conversations" / "project_harbor").glob("*.json"))
    assert len(after) == len(before)
    broken = tmp_path / "broken.md"
    broken.write_text("no labels here", encoding="utf-8")
    try:
        memory.import_conversation("project_harbor", broken)
        failed = False
    except StorageError:
        failed = True
    assert failed
    memory.close()


def test_parse_json_normalized_shape() -> None:
    origin, turns = parse_transcript(
        Path("chat.json"),
        json.dumps({"turns": [{"role": "user", "content": "Hello Harbor."}]}),
    )
    assert origin == "json"
    assert turns[0].content == "Hello Harbor."
    assert extract_candidates(turns)
