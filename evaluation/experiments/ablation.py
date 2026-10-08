"""Ablation A-E on the System B path. No MCP."""

from __future__ import annotations

import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from agent.llm import HeuristicChat
from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import run_direct
from evaluation.baselines.stateless_rag import run_stateless
from evaluation.datasets.controlled.load import HARBOR, load_harbor, load_questions
from evaluation.experiments.compare import prompt_fingerprint
from evaluation.metrics.agent import score_item
from ingestion.indexing.pipeline import index_project

REPORTS = Path(__file__).resolve().parents[1] / "reports"
ROWS: list[tuple[str, str, str]] = [
    ("A", "chunks", "No persistent memory. Same as System A."),
    ("B", "conversations", "Raw conversation turns only."),
    ("C", "structured", "Structured records only; no episodes or documents."),
    ("D", "structured_episodic", "Structured plus episodic memory; no document RAG."),
    ("E", "full", "Structured, episodic, and document RAG. Full System B."),
]
INTERPRETATIONS = {
    "A": "Chunks-only baseline: no stored Harbor decisions or facts.",
    "B": "Transcript overlap can surface import asides but not structured decisions.",
    "C": "Structured memory is the first condition that can answer seeded decision/fact items.",
    "D": "Episodes add narrative context; Harbor gold is mostly structured, so gains are small.",
    "E": "Adding document RAG recovers corpus-only items that memory cannot answer.",
}


def run_ablation(
    data_root: Path,
    *,
    question_ids: list[str] | None = None,
) -> dict:
    load_harbor(data_root)
    embedder = HashEmbedder()
    llm = HeuristicChat()
    index_project(data_root, HARBOR, embedder=embedder)
    memory = MemoryRepository(data_root)
    documents = DocumentRepository(data_root, memory.index)
    questions = load_questions()
    if question_ids:
        questions = [item for item in questions if item.id in set(question_ids)]
    scores = []
    latencies: dict[str, list[float]] = {label: [] for label, _, _ in ROWS}
    try:
        for item in questions:
            prior = [turn.model_dump() for turn in item.prior_turns]
            for label, mode, _desc in ROWS:
                started = perf_counter()
                if mode == "chunks":
                    result = run_stateless(
                        project_id=HARBOR,
                        message=item.question,
                        documents=documents,
                        embedder=embedder,
                        llm=llm,
                        prior_turns=prior,
                    )
                    scored = score_item(item, result, "A")
                else:
                    result = run_direct(
                        project_id=HARBOR,
                        message=item.question,
                        memory=memory,
                        documents=documents,
                        embedder=embedder,
                        llm=llm,
                        prior_turns=prior,
                        thread_id=f"abl-{label}-{item.id}",
                        ablation=mode,  # type: ignore[arg-type]
                    )
                    scored = score_item(item, result, "B")
                latencies[label].append(perf_counter() - started)
                scores.append(
                    {
                        "label": label,
                        "item_id": item.id,
                        "task": scored.task_completion,
                        "grounded": scored.grounded,
                    }
                )
    finally:
        documents.close()
        memory.close()
    return {
        "scores": scores,
        "latencies": latencies,
        "prompts": prompt_fingerprint(),
        "item_ids": [item.id for item in questions],
    }


def render_ablation(result: dict) -> str:
    lines = [
        "# Harbor memory ablation",
        "",
        "System B call path only. Prompts frozen:",
    ]
    for name, digest in result["prompts"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.append("")
    lines.append("Chat/embed: HeuristicChat + HashEmbedder (offline).")
    lines.append("")
    lines.append("| Condition | What it may read | Task completion | Grounded | Median latency (s) | Flipped vs previous |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    previous: set[str] = set()
    prev_n = 0
    by_label: dict[str, list[dict]] = {}
    for row in result["scores"]:
        by_label.setdefault(row["label"], []).append(row)
    for label, _mode, desc in ROWS:
        rows = by_label.get(label, [])
        n = len(rows) or 1
        task = sum(item["task"] for item in rows) / n
        grounded = sum(item["grounded"] for item in rows) / n
        passed = {item["item_id"] for item in rows if item["task"]}
        if prev_n == 0:
            flipped = "n/a"
        else:
            gained = sorted(passed - previous)
            lost = sorted(previous - passed)
            flipped = f"+{gained} -{lost}" if gained or lost else "none"
        previous = passed
        prev_n = n
        med = float(median(result["latencies"][label])) if result["latencies"][label] else 0.0
        lines.append(f"| {label} | {desc} | {task:.2f} | {grounded:.2f} | {med:.3f} | {flipped} |")
    lines.extend(["", "## Interpretation", ""])
    for label, text in INTERPRETATIONS.items():
        lines.append(f"- **{label}.** {text}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_ablation(result: dict, path: Path | None = None) -> Path:
    target = path or (REPORTS / "ablation.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_ablation(result), encoding="utf-8")
    return target


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="memoria-ablation-") as tmp:
        result = run_ablation(Path(tmp))
        path = write_ablation(result)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
