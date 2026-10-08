"""Phase 15-style resource measurements. No extra pip packages."""

from __future__ import annotations

import ctypes
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from agent.llm import OllamaChat
from core.memory.content import sha256_bytes
from core.ollama import OllamaEmbedder
from core.retrieval.hash_embedder import HashEmbedder
from core.retrieval.search import search_documents
from core.schemas.documents import DocumentMeta
from core.storage.documents import DocumentRepository, new_document_id
from core.storage.memory_repo import MemoryRepository
from evaluation.baselines.stateless_rag import run_stateless
from evaluation.datasets.controlled.load import CONTROLLED_ROOT, HARBOR, load_harbor
from ingestion.indexing.pipeline import index_project

REPORTS = Path(__file__).resolve().parents[1] / "evaluation" / "reports"
SCALES = (10, 100, 500, 1000)
HONORS_CHAT = "phi3:mini"
HONORS_EMBED = "nomic-embed-text"


def _rss_mb() -> float:
    if sys.platform == "win32":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        get_mem = ctypes.windll.psapi.GetProcessMemoryInfo
        get_mem.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        get_mem.restype = ctypes.c_int
        handle = ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess())
        if not get_mem(handle, ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.WorkingSetSize / (1024 * 1024)
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def _vault_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _peak_during(action):
    start = _rss_mb()
    t0 = perf_counter()
    result = action()
    elapsed = perf_counter() - t0
    end = _rss_mb()
    return result, elapsed, start, end, max(start, end)


def measure(output: Path | None = None) -> str:
    idle = _rss_mb()
    lines = [
        "# Resource measurements",
        "",
        "Idle RSS is this Python process before Harbor work. Scale indexing uses HashEmbedder copies of Harbor text so 1000 live Ollama embeds are not required on 8 GB RAM. One live Harbor index + one `phi3:mini` turn is reported separately when Ollama responds.",
        "",
        f"- Idle RSS: {idle:.1f} MB",
        "",
    ]
    with tempfile.TemporaryDirectory(prefix="memoria-res-") as tmp:
        root = Path(tmp)
        load_harbor(root)
        try:
            embedder = OllamaEmbedder(model=HONORS_EMBED)

            def index_live():
                return index_project(root, HARBOR, embedder=embedder)

            _report, idx_s, idx_start, idx_end, idx_peak = _peak_during(index_live)
            docs = DocumentRepository(root)

            def query():
                return search_documents(docs, HARBOR, "Harbor RAM", embedder, limit=5)

            hits, q_s, _qs, _qe, q_peak = _peak_during(query)
            chat = OllamaChat(model=HONORS_CHAT)

            def llm():
                return run_stateless(
                    project_id=HARBOR,
                    message="How much RAM does the Harbor workstation have?",
                    documents=docs,
                    embedder=embedder,
                    llm=chat,
                )

            turn, llm_s, _ls, _le, llm_peak = _peak_during(llm)
            docs.close()
            lines.extend(
                [
                    "## Live Harbor (nomic-embed-text + phi3:mini)",
                    "",
                    f"- Indexing: {idx_s:.2f} s, RSS start/end/peak {idx_start:.1f}/{idx_end:.1f}/{idx_peak:.1f} MB",
                    f"- Retrieval: {q_s * 1000:.1f} ms, hits={len(hits)}, RSS peak {q_peak:.1f} MB",
                    f"- Stateless LLM turn: {llm_s:.2f} s, RSS peak {llm_peak:.1f} MB, answer_chars={len(turn.answer)}",
                    "",
                ]
            )
        except Exception as exc:
            lines.extend(
                [
                    "## Live Harbor",
                    "",
                    f"TODO: live nomic/phi3 measurement failed ({exc}). Scale table below still ran with HashEmbedder.",
                    "",
                ]
            )

    lines.extend(
        [
            "## Indexing scale (HashEmbedder)",
            "",
            "| Documents | Index time (s) | Vault bytes | Peak RSS (MB) |",
            "| --- | --- | --- | --- |",
        ]
    )
    source = CONTROLLED_ROOT / "documents"
    originals = list(source.glob("*"))
    hash_embedder = HashEmbedder()
    for count in SCALES:
        with tempfile.TemporaryDirectory(prefix=f"memoria-n{count}-") as tmp:
            root = Path(tmp)
            load_harbor(root)
            memory = MemoryRepository(root)
            store = DocumentRepository(root, memory.index)
            existing = store.list(HARBOR)
            needed = count - len(existing)
            extra = 0
            while needed > 0:
                src = originals[extra % len(originals)]
                extra += 1
                data = src.read_bytes()
                doc_id = new_document_id()
                directory = root / "documents" / HARBOR / doc_id
                directory.mkdir(parents=True, exist_ok=True)
                (directory / f"original{src.suffix or '.txt'}").write_bytes(data)
                store.add(
                    DocumentMeta(
                        id=doc_id,
                        project_id=HARBOR,
                        filename=src.name,
                        file_type="markdown" if src.suffix == ".md" else "text",
                        byte_size=len(data),
                        content_hash=sha256_bytes(data),
                        indexed_at=None,
                        status="pending",
                        error=None,
                        chunk_count=0,
                        vault_relpath=f"documents/{HARBOR}/{doc_id}",
                    )
                )
                needed -= 1

            def run_index():
                return index_project(root, HARBOR, embedder=hash_embedder)

            _rep, secs, _s, _e, peak = _peak_during(run_index)
            size = _vault_bytes(root)
            n = len(store.list(HARBOR))
            store.close()
            memory.close()
            lines.append(f"| {n} | {secs:.2f} | {size} | {peak:.1f} |")
    lines.extend(["", f"Idle RSS after measurements: {_rss_mb():.1f} MB", ""])
    text = "\n".join(lines) + "\n"
    target = output or (REPORTS / "resources.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(measure())
