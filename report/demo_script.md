# Speaker notes (5–7 minutes)

Match [scripts/demo_end_to_end.md](../scripts/demo_end_to_end.md). URL: **http://localhost:8501**. Prep: `.\scripts\start_demo.ps1` with Harbor seeded.

**0:00 Intro.** “Memoria is a local copilot: Streamlit on 8501, one custom MCP server on 8765, SQLite exact cosine, Ollama on the host. No cloud APIs. Hardware story is 8 GB RAM.”

**0:45 Documents.** Sidebar project `project_harbor` → **Documents**. Ten Harbor files, status `indexed`.

**1:15 Chat + Trace.** **Chat**, System **C**, check **Use Ollama chat**. Click **Send** once. A cold `phi3:mini` load on this CPU was about 3 minutes; a turn with the model already resident was about 2 minutes. Narrate that as the 8 GB constraint. Do not send again while the spinner is up.

Ask: **How much RAM does the Harbor workstation have?**

Expected answer: **8 GB**. Live caption on the seeded vault: `known_from_memory` / `memory`, because that fact is stored. **Trace** shows `memory.search` and the fact id. The document-route example is *What retrieval method does Harbor use for document vectors?* — observed `documents.search`, chunk ids, exact cosine in SQLite.

**3:00 Memory.** **Memory** page: seeded `decision_a11ce0000001` (exact cosine in SQLite), `fact_8ba000000001` (8 GB RAM).

**3:45 Restart.** `docker compose down` then `up -d`. Chat history gone; YAML/SQLite remain.

**4:30 Recall.** Ask: **What architecture did I decide for the retrieval system?**

Expected: **exact cosine** and **SQLite**. Not Qdrant.

**5:30 Comparison.** A = stateless RAG. B = persistent memory without MCP. C = same memory through MCP. The independent variable is structured memory; MCP is the production boundary.

**6:15 Resources.** One chat model resident, embeddings `keep_alive: 0`, two Compose processes, Ollama on the host.

Do not mix this live vault with frozen evaluation Recall tables.
