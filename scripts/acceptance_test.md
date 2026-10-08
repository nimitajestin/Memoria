# Memoria acceptance test (15 conditions)

Run after `.\scripts\start_demo.ps1` (or the Unix launcher) with Harbor seeded into `storage/` (see README first-time setup). Use Chrome at **http://localhost:8501**.

Record each row in `report/acceptance_results.md` during T4. Do not skip a FAIL: stop and report the condition id.

| # | Condition | Expected result | Pass / Fail | Timing |
| --- | --- | --- | --- | --- |
| 1 | Ollama running | `ollama list` succeeds against the local daemon | | |
| 2 | Both models present | `ollama list` shows `phi3:mini` and `nomic-embed-text` | | |
| 3 | Compose up | `docker compose up --build -d` (or the launcher) exits 0; `docker compose ps` shows `mcp` and `app` | | |
| 4 | MCP :8765 | TCP connect to `127.0.0.1:8765` succeeds (Streamable HTTP at `/mcp`) | | |
| 5 | Streamlit :8501 | TCP/HTTP to `127.0.0.1:8501` succeeds | | |
| 6 | Browser loads | Chrome opens http://localhost:8501 and shows the Memoria title | | |
| 7 | Chat works | Chat page: send a short message; an answer (or explicit error) renders, no crash | | |
| 8 | Memory works | Memory page lists seeded Harbor records (types/ids visible) | | |
| 9 | Documents works | Documents page lists Harbor files with statuses/chunk counts | | |
| 10 | Trace works | After a Chat send, Trace page shows JSON node trace (not the empty-state caption only) | | |
| 11 | Harbor docs index | At least one document status is `indexed` with `chunk_count` > 0 | | |
| 12 | RAG question returns grounded answer | System **C**, **Use Ollama chat** on, project `project_harbor`. Ask: *How much RAM does the Harbor workstation have?* Answer includes **8 GB** and caption `grounding=` is document-side (`known_from_documents` or equivalent, not a crash) | | |
| 13 | Trace shows MCP ops + evidence | Same turn: Trace includes retrieve/MCP-related entries; Chat/trace mentions evidence ids (chunk or memory ids) | | |
| 14 | Memory write + restart + recall | Ask a rememberable fact, or rely on seeded decision. `docker compose down` then `docker compose up -d`. Memory page still lists YAML records. Follow-up: *What architecture did I decide for the retrieval system?* Answer includes **exact cosine** and **SQLite** | | |
| 15 | No cloud APIs | Traffic is localhost/Ollama/Docker only (no OpenAI/Anthropic keys in `.env`; `OLLAMA_BASE_URL` is host Ollama) | | |

## Manual procedure if the agent cannot drive Chrome

1. Start Ollama. Confirm conditions 1–2.
2. From the repo root: `.\scripts\start_demo.ps1`.
3. Open http://localhost:8501.
4. Walk rows 6–15. Screenshot Chat, Memory, Documents, Trace into `report/screenshots/{chat,memory,documents,trace}.png`.
5. Copy this table into `report/acceptance_results.md` with Pass/Fail and wall times.

## Fail policy

A FAIL is a genuine product breakage (crash, empty crash loop, wrong port, vault wiped on restart). Slow first Ollama query is not a FAIL if the answer eventually matches. Report FAIL line ids only; fixes stay minimal and one commit each.
