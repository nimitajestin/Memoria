# Memoria

Local-first agentic knowledge copilot with one custom MCP memory server, aimed at an 8 GB RAM, CPU-only machine.

The research question is whether structured project memory, exposed through a single MCP server, improves a local RAG agent compared with stateless RAG, under a hard RAM budget and with no cloud APIs.

## Specification

- [Architecture](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [Data schemas](docs/schemas.md)
- [MCP interface](docs/mcp-interface.md)
- [Evaluation design](docs/evaluation-design.md)

## Status

Execution is accuracy-first. Architecture ADRs are unchanged.

| Order | Phase | State |
| --- | --- | --- |
| — | 0 Architecture | Frozen in `docs/` |
| — | 1 Storage | Implemented in `core/` |
| 1 | 9a Harbor dataset | Implemented |
| 2 | 3 Ingestion | Implemented |
| 3 | 4 Retrieval | Implemented |
| 4 | 2 MCP | Implemented |
| 5 | 5 Agent (A, then B, then C) | Implemented |
| 6 | 6 Remember | Implemented |
| 7 | 7 Import | Implemented |
| 8 | 9b Experiment runners | Implemented |
| 9 | 10 Reliability | Implemented |
| 10 | 8 UI | Implemented |
| 11 | 11 Docker | Implemented |
| 12 | 12 Finalization | Implemented |

## Phase 1

The vault stores project memory as YAML. `status.md` and `decisions.md` are generated views. SQLite at `storage/index/memoria.sqlite` indexes those records and holds document metadata, chunk text, and embedding blobs. Writes are atomic, revision-checked, and refused when a path leaves the data root.

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

Phase 4 retrieval is exact cosine over SQLite float32 vectors. Default tests use a hash embedder; Ollama is optional (`pytest -m ollama`).

```powershell
python -m pytest
streamlit run app/ui/streamlit_app.py
python -m mcp_server
docker compose up --build
```

Offline A/B/C scoring (HeuristicChat, not the reported Ollama run):

```powershell
python -c "from pathlib import Path; from evaluation.experiments.compare import run_comparison, write_report; write_report(run_comparison(Path('storage')))"
```




