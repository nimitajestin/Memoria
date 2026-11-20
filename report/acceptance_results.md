# T4 browser acceptance results

Rows 1–9 and 14–15 are the 2026-10-08 pass. Rows 10–13 and the browser section are the 2026-11-20 desktop Chrome pass on branch `file-ingest`. Demo URL: http://localhost:8501. Models: chat `phi3:mini`, embed `nomic-embed-text`. Compose services `mcp` :8765 and `app` :8501.

First-run embarrassments that were fixed (each has its own commit):

1. Docker image missing `PYTHONPATH=/app` → Streamlit `ModuleNotFoundError: No module named 'app'`.
2. `python scripts/rebuild_index.py` failed with `No module named 'core'` until sys.path was set.
3. Compose did not pass `LLM_MODEL`; host had `phi3:mini` not `qwen2.5:3b`.
4. Sidebar defaulted to `project_decoy` (empty Harbor). Now prefers `project_harbor`.
5. Streamlit **Deploy** toolbar (hidden via `.streamlit/config.toml`).

| # | Condition | Expected | Result | Timing | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Ollama running | `ollama list` works | **PASS** | ~2 s | Local daemon |
| 2 | Both models present | `phi3:mini`, `nomic-embed-text` | **PASS** | ~2 s | Also has `qwen2.5:7b` unused |
| 3 | Compose up | `mcp` + `app` started | **PASS** | first build ~6 min; later up ~11 s | `.\scripts\start_demo.ps1` |
| 4 | MCP :8765 | TCP open | **PASS** | < 3 s after start | Streamable HTTP `/mcp` |
| 5 | Streamlit :8501 | TCP/HTTP open | **PASS** | < 5 s after start | Title Memoria |
| 6 | Browser loads | Memoria UI | **PASS** | ~4 s | Cursor browser + Chrome URL |
| 7 | Chat works | Chat page, no crash | **PASS** | — | Controls render (System, Ollama, Message, Send) |
| 8 | Memory works | Seeded records | **PASS** | ~2 s | 8 active Harbor records |
| 9 | Documents works | Harbor files listed | **PASS** | ~2 s | 10 documents |
| 10 | Trace works | JSON after a send; empty-state otherwise | **PASS** (desktop Chrome, 2026-11-20) | — | Trace shows the last browser turn. Empty caption only before the first Send |
| 11 | Harbor docs indexed | status indexed, chunks > 0 | **PASS** | index 22 s | All 10 indexed. Re-checked in Chrome 2026-11-20: 10 documents, chunk counts > 0 |
| 12 | RAG grounded answer | 8 GB | **PASS** (desktop Chrome Send) | cold wall clock about 3 min | System C, Use Ollama chat, `project_harbor`. Question: *How much RAM does the Harbor workstation have?* Answer **8 GB**. Caption `grounding=known_from_memory route=memory`. `ollama ps` was empty before Send. The page said it loaded `phi3:mini`, then “Running this turn.” The seeded fact `fact_8ba000000001` is why the live route is memory. Dataset gold remains documents; that table was not changed |
| 13 | Trace MCP + evidence | retrieve + ids | **PASS** (same browser session) | included above | RAM turn Trace: `memory.search`, memory ids including `fact_8ba000000001`, empty `chunk_ids`. Document turn (below) Trace: `documents.search` and five chunk ids. `mcp` logged `POST /mcp` 200 from the app container for both turns |
| 14 | Restart + recall | vault intact; architecture question | **PASS** (vault) / **PASS** (recall via MCP path) | down/up **11.3 s** | After `docker compose down` / `up -d`: still 8 memory records and 10 indexed docs. Architecture answer is seeded `decision_a11ce0000001` (exact cosine / SQLite). Streamlit session history cleared as designed |
| 15 | No cloud APIs | localhost / Ollama / Docker only | **PASS** | — | `OLLAMA_BASE_URL=http://host.docker.internal:11434`; no vendor keys in Compose |

## Screenshots

- `report/screenshots/chat.png` — Chat, `project_harbor`
- `report/screenshots/memory.png` — 8 Harbor records
- `report/screenshots/documents.png` — 10 indexed documents
- `report/screenshots/trace.png` — 2026-10-08 empty-state. Not the 2026-11-20 Trace. No new screenshot file was saved.

## Browser Send, 2026-11-20 (desktop Chrome)

Embedded-browser clicks do not start a Streamlit run. These two turns were submitted in desktop Chrome with the form **Send** control (Ctrl+Enter does the same). System **C**, **Use Ollama chat** checked, project `project_harbor`.

Load and inference are separate. `OLLAMA_LOAD_TIMEOUT` defaults to 180 seconds and is used only to load a model that is not already in `ollama ps`. `OLLAMA_INFERENCE_TIMEOUT` defaults to 90 seconds per generation. The page shows “Checking whether phi3:mini is loaded…”, then either “Loaded …” or “already loaded”, then “Running this turn. Leave this page open and do not send again.” A second Send that arrives during that run is not sent again. A red error is the failed turn; it is not appended to history.

| Turn | Model state before Send | What the page showed | Answer | Trace |
| --- | --- | --- | --- | --- |
| RAM question | `ollama ps` empty | Loaded `phi3:mini`, then the running spinner. About 3 minutes wall clock (15:28–15:31), not a stopwatch | `8 GB`. `grounding=known_from_memory route=memory` | `memory.search`; memory ids; no chunk ids. MCP: three `POST /mcp` 200 |
| *What retrieval method does Harbor use for document vectors?* | `phi3:mini` already resident, context 1024 | “phi3:mini is already loaded. The next step is the reply.” About 2 minutes wall clock (15:39–15:41) | “Harbor uses exact cosine search over float32 vectors stored in SQLite for document vector retrieval.” `grounding=known_from_documents route=documents` | `documents.search`; five `chunk_` ids; citations on the answer node; `remember` outcome `skip` (question ends in `?`). MCP: three more `POST /mcp` 200, and the MCP server called Ollama `/api/embed` 200 |

Not re-checked in this pass: the restart-and-recall row, a forced Ollama failure in the browser, and new screenshot files.
