# Seminar demo (5–7 minutes)

Audience: honors committee. Hardware: 8 GB RAM, CPU, local Ollama, Docker Compose. No cloud APIs.

**Prep (before the room):** `ollama pull phi3:mini`, `ollama pull nomic-embed-text`, Harbor seeded + indexed, `.\scripts\start_demo.ps1`. Browser already on http://localhost:8501.

| Minute | Beat | What you do | What they should see |
| --- | --- | --- | --- |
| 0:00 | Intro | One sentence: local agent, one custom MCP server on :8765, SQLite exact cosine, Streamlit on :8501. | Tab title Memoria; sidebar Chat / Memory / Documents / Trace |
| 0:45 | Documents | Open **Documents**, project `project_harbor`. | Harbor files listed, `indexed`, chunk counts > 0 |
| 1:15 | Chat + Trace | **Chat**: System **C**, check **Use Ollama chat**. Click **Send** once (or Ctrl+Enter). Leave the page open. Ask: **How much RAM does the Harbor workstation have?** Then open **Trace**. If `phi3:mini` is not already in `ollama ps`, this cold turn was about 3 minutes. With the model already resident, a following turn was about 2 minutes. | Answer **8 GB**. On this seeded vault the caption is `grounding=known_from_memory route=memory` because `fact_8ba000000001` is stored. Trace lists `memory.search` and that fact id. For a document route, ask **What retrieval method does Harbor use for document vectors?** Observed answer names exact cosine over float32 vectors in SQLite, caption `grounding=known_from_documents route=documents`, Trace tool `documents.search` plus chunk ids |
| 3:00 | Memory write | Stay on Chat. Optional: state a durable preference if the remember node fires. Then open **Memory**. | Seeded records visible (`decision_…`, `fact_…`). If a new record appears, name its id |
| 3:45 | Restart | `docker compose down` then `docker compose up -d` (or re-run the launcher). Reload the browser. Session chat history is gone; vault is not. | **Memory** and **Documents** still populated |
| 4:30 | Recall | Chat again (System C, Ollama on). Ask exactly: **What architecture did I decide for the retrieval system?** | Answer contains **exact cosine** and **SQLite**. Not Qdrant. Grounding from memory |
| 5:30 | Comparison slide | Point at `evaluation/reports/` (or the report). Systems A (stateless RAG) vs B (direct memory) vs C (MCP). | One line: structured persistent memory is the independent variable; MCP is the production boundary |
| 6:15 | Resource slide | 8 GB: one chat model resident, embeddings `keep_alive: 0`, two Compose processes, Ollama on the host. | Stay inside the hardware story; do not claim a cloud eval |

## Exact questions and expected answers

1. **How much RAM does the Harbor workstation have?**  
   Expected answer: **8 GB**. Forbidden: 16 GB.  
   Live browser caption on the seeded vault: `grounding=known_from_memory route=memory` (`fact_8ba000000001`). The controlled-question gold label is still documents; do not edit that dataset to match the live route.

2. **What architecture did I decide for the retrieval system?**  
   Expected: **exact cosine** in **SQLite** (seeded decision `decision_a11ce0000001`). Forbidden: Qdrant.

Do not mix evaluation Recall tables with this live vault. Seeded Harbor memory is the restart story.

## If something stalls

- Cold model: the page checks `ollama ps`, loads with `OLLAMA_LOAD_TIMEOUT` (default 180s), then generates with `OLLAMA_INFERENCE_TIMEOUT` (default 90s per call). Warm model: the caption says it is already loaded and skips the load. One Send only; a second click during the run is dropped. A red error means that turn was not saved. Observed cold RAM turn about 3 minutes; observed warm document turn about 2 minutes. Warm `phi3:mini` before the room if the slot is short.
- Empty documents: seed + `python scripts/rebuild_index.py` (README).
- Port busy: `docker compose down` and retry the launcher.
