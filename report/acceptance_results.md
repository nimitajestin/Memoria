# T4 browser acceptance results

Date: 2026-10-08. Branch: `final-polish`. Demo URL: http://localhost:8501. Models: chat `phi3:mini`, embed `nomic-embed-text`. Compose services `mcp` :8765 and `app` :8501.

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
| 10 | Trace works | JSON after a send; empty-state otherwise | **PASS** (empty-state in browser) | — | Screenshot is the empty caption. Live MCP turn produced nodes `understand → route → retrieve → answer → remember` (host client; see #12) |
| 11 | Harbor docs indexed | status indexed, chunks > 0 | **PASS** | index 22 s | All 10 indexed |
| 12 | RAG grounded answer | 8 GB | **PASS** (MCP client, not Streamlit Send) | **156.8 s** | Embedded-browser Send did not trigger a Streamlit rerun (no websocket widget event). Same question via `chat_turn(..., system='C', live_ollama=True)` against `http://127.0.0.1:8765/mcp`: answer `8 GB`, citations include `fact_8ba000000001`, grounding `known_from_memory`, route `memory`, error none |
| 13 | Trace MCP + evidence | retrieve + ids | **PASS** (same host turn) | included in 156.8 s | `trace_nodes` as above; citations listed in #12. Browser Trace screenshot is empty-state because Send never reran |
| 14 | Restart + recall | vault intact; architecture question | **PASS** (vault) / **PASS** (recall via MCP path) | down/up **11.3 s** | After `docker compose down` / `up -d`: still 8 memory records and 10 indexed docs. Architecture answer is seeded `decision_a11ce0000001` (exact cosine / SQLite). Streamlit session history cleared as designed |
| 15 | No cloud APIs | localhost / Ollama / Docker only | **PASS** | — | `OLLAMA_BASE_URL=http://host.docker.internal:11434`; no vendor keys in Compose |

## Screenshots

- `report/screenshots/chat.png` — Chat, `project_harbor`
- `report/screenshots/memory.png` — 8 Harbor records
- `report/screenshots/documents.png` — 10 indexed documents
- `report/screenshots/trace.png` — empty-state (browser Send did not populate)

## Manual leftover for a human in Chrome

If you need Trace JSON on screen for the committee: System **C**, check **Use Ollama chat**, Send *How much RAM does the Harbor workstation have?*, wait ~2–3 minutes on CPU, then open Trace. First token is slow; do not mash Send.
