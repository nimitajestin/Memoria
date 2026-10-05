"""Offline A/B/C Harbor comparison. Prompts are the files under agent/prompts/."""

from __future__ import annotations

import hashlib
from pathlib import Path
from time import perf_counter

from agent.graph.build import build_graph, run_turn
from agent.llm import HeuristicChat, OllamaChat
from agent.mcp_client import MCPBackend
from core.retrieval.hash_embedder import HashEmbedder
from core.storage.documents import DocumentRepository
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.direct_memory import DirectBackend, run_direct
from evaluation.baselines.stateless_rag import run_stateless
from evaluation.datasets.controlled.load import HARBOR, load_harbor, load_questions
from evaluation.metrics.agent import ItemScore, score_item
from ingestion.indexing.pipeline import index_project
from mcp_server.server import build_server

PROMPT_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
REPORTS = Path(__file__).resolve().parents[1] / "reports"


def prompt_fingerprint() -> dict[str, str]:
    hashes = {}
    for path in sorted(PROMPT_DIR.glob("*.md")):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return hashes


def run_comparison(
    data_root: Path,
    *,
    llm=None,
    question_ids: list[str] | None = None,
    live_ollama: bool = False,
) -> dict:
    load_harbor(data_root)
    embedder = HashEmbedder()
    index_project(data_root, HARBOR, embedder=embedder)
    memory = MemoryRepository(data_root)
    documents = DocumentRepository(data_root, memory.index)
    server = build_server(data_root, embedder)
    chat = llm or (OllamaChat() if live_ollama else HeuristicChat())
    questions = load_questions()
    if question_ids:
        wanted = set(question_ids)
        questions = [item for item in questions if item.id in wanted]
    rows: list[ItemScore] = []
    latencies: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    for item in questions:
        prior = [turn.model_dump() for turn in item.prior_turns]
        started = perf_counter()
        a = run_stateless(
            project_id=HARBOR,
            message=item.question,
            documents=documents,
            embedder=embedder,
            llm=chat,
            prior_turns=prior,
        )
        latencies["A"].append(perf_counter() - started)
        rows.append(score_item(item, a, "A"))
        started = perf_counter()
        b = run_direct(
            project_id=HARBOR,
            message=item.question,
            memory=memory,
            documents=documents,
            embedder=embedder,
            llm=chat,
            prior_turns=prior,
            thread_id=f"b-{item.id}",
        )
        latencies["B"].append(perf_counter() - started)
        rows.append(score_item(item, b, "B"))
        started = perf_counter()
        c = run_turn(
            build_graph(MCPBackend(server=server), chat),
            project_id=HARBOR,
            message=item.question,
            prior_turns=prior,
            thread_id=f"c-{item.id}",
        )
        latencies["C"].append(perf_counter() - started)
        rows.append(score_item(item, c, "C"))
    memory.close()
    return {
        "scores": rows,
        "latencies": latencies,
        "prompts": prompt_fingerprint(),
        "live_ollama": live_ollama,
        "item_ids": [item.id for item in questions],
    }


def summarize(rows: list[ItemScore], system: str) -> dict[str, float]:
    subset = [row for row in rows if row.system == system]
    n = len(subset) or 1
    route_rows = [row.route_ok for row in subset if row.route_ok is not None]
    return {
        "task_completion": sum(row.task_completion for row in subset) / n,
        "grounded": sum(row.grounded for row in subset) / n,
        "tool_selection": (sum(1 for item in route_rows if item) / len(route_rows)) if route_rows else None,
        "error_rate": sum(row.error for row in subset) / n,
        "n": len(subset),
    }


def render_comparison(result: dict) -> str:
    lines = [
        "# Harbor system comparison",
        "",
        "Prompts frozen at these content hashes:",
    ]
    for name, digest in result["prompts"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.append("")
    lines.append(f"Chat: {'Ollama' if result['live_ollama'] else 'HeuristicChat (offline)'}")
    lines.append("")
    lines.append("| System | Task completion | Grounded | Tool selection | Error rate | Median latency (s) |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for system in ("A", "B", "C"):
        stats = summarize(result["scores"], system)
        times = sorted(result["latencies"][system])
        median = times[len(times) // 2] if times else 0.0
        tool = "n/a" if stats["tool_selection"] is None else f"{stats['tool_selection']:.2f}"
        lines.append(
            f"| {system} | {stats['task_completion']:.2f} | {stats['grounded']:.2f} | {tool} | {stats['error_rate']:.2f} | {median:.3f} |"
        )
    lines.extend(["", "## Item outcomes", "", "| Item | System | Task | Route | Grounded |", "| --- | --- | --- | --- | --- |"])
    for row in result["scores"]:
        route = "n/a" if row.route_ok is None else str(row.route_ok)
        lines.append(f"| {row.item_id} | {row.system} | {row.task_completion} | {route} | {row.grounded} |")
    lines.extend(
        [
            "",
            "Ablation note: System A is condition A (chunks only). System B is condition E (structured, episodic, and document RAG). Raw-conversation and structured-only rows are reserved for a follow-up ablation pass on the System B path.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(result: dict, path: Path | None = None) -> Path:
    target = path or (REPORTS / "comparison.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_comparison(result), encoding="utf-8")
    return target
