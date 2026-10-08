# Seminar demo (5–7 minutes)

Audience: honors committee. Hardware: 8 GB RAM, CPU, local Ollama, Docker Compose. No cloud APIs.

**Prep (before the room):** `ollama pull phi3:mini`, `ollama pull nomic-embed-text`, Harbor seeded + indexed, `.\scripts\start_demo.ps1`. Browser already on http://localhost:8501.

| Minute | Beat | What you do | What they should see |
| --- | --- | --- | --- |
| 0:00 | Intro | One sentence: local agent, one custom MCP server on :8765, SQLite exact cosine, Streamlit on :8501. | Tab title Memoria; sidebar Chat / Memory / Documents / Trace |
| 0:45 | Documents | Open **Documents**, project `project_harbor`. | Harbor files listed, `indexed`, chunk counts > 0 |
| 1:15 | RAG + Trace | **Chat**: System **C**, check **Use Ollama chat**. First token may take 1–2 min (CPU). Ask exactly: **How much RAM does the Harbor workstation have?** Then open **Trace**. | Answer contains **8 GB**. Caption `grounding=known_from_documents` (or documents-side). Trace JSON shows retrieve / MCP tool activity and evidence ids |
| 3:00 | Memory write | Stay on Chat. Optional: state a durable preference if the remember node fires. Then open **Memory**. | Seeded records visible (`decision_…`, `fact_…`). If a new record appears, name its id |
| 3:45 | Restart | `docker compose down` then `docker compose up -d` (or re-run the launcher). Reload the browser. Session chat history is gone; vault is not. | **Memory** and **Documents** still populated |
| 4:30 | Recall | Chat again (System C, Ollama on). Ask exactly: **What architecture did I decide for the retrieval system?** | Answer contains **exact cosine** and **SQLite**. Not Qdrant. Grounding from memory |
| 5:30 | Comparison slide | Point at `evaluation/reports/` (or the report). Systems A (stateless RAG) vs B (direct memory) vs C (MCP). | One line: structured persistent memory is the independent variable; MCP is the production boundary |
| 6:15 | Resource slide | 8 GB: one chat model resident, embeddings `keep_alive: 0`, two Compose processes, Ollama on the host. | Stay inside the hardware story; do not claim a cloud eval |

## Exact questions and expected answers

1. **How much RAM does the Harbor workstation have?**  
   Expected: **8 GB** (Harbor `MARKER_HW_RAM` / hardware.md). Forbidden: 16 GB.

2. **What architecture did I decide for the retrieval system?**  
   Expected: **exact cosine** in **SQLite** (seeded decision `decision_a11ce0000001`). Forbidden: Qdrant.

Do not mix evaluation Recall tables with this live vault. Seeded Harbor memory is the restart story.

## If something stalls

- First Ollama call after compose: wait; do not mash Send.
- Empty documents: seed + `python scripts/rebuild_index.py` (README).
- Port busy: `docker compose down` and retry the launcher.
