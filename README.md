# Memoria

Local-first agentic knowledge copilot with one custom MCP memory server, aimed at an 8 GB RAM, CPU-only machine.

The research question is whether structured project memory, exposed through a single MCP server, improves a local RAG agent compared with stateless RAG, under a hard RAM budget and with no cloud APIs.

## Run the Demo

One command from the repo root (Windows):

```powershell
.\scripts\start_demo.ps1
```

Unix:

```bash
chmod +x scripts/start_demo.sh
./scripts/start_demo.sh
```

The launcher checks that Ollama is up and that `phi3:mini` and `nomic-embed-text` are installed, runs `docker compose up --build -d`, waits until MCP `:8765` and Streamlit `:8501` accept connections, then prints:

```text
Memoria is running at http://localhost:8501
```

### Browser URL

Open **http://localhost:8501** in Chrome (or another current browser). Use the sidebar pages Chat, Memory, Documents, and Trace. For the seminar path, pick project `project_harbor`, system **C**, and check **Use Ollama chat**.

Seminar checklist and spoken script: [scripts/acceptance_test.md](scripts/acceptance_test.md), [scripts/demo_end_to_end.md](scripts/demo_end_to_end.md).

## First-time setup

1. Install Python 3.11+, [Ollama](https://ollama.com), and Docker Desktop.
2. Pull the demo models (honors chat substitution; embeddings match the ADR-005 default):

```powershell
ollama pull phi3:mini
ollama pull nomic-embed-text
```

Settings/ADR chat default remains `qwen2.5:3b`. To use that model instead, `ollama pull qwen2.5:3b` and set `LLM_MODEL` in `.env`.

3. Install Python deps (local pytest / seed, not required inside Compose):

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

4. Copy environment defaults if you run outside Docker:

```powershell
copy .env.example .env
```

5. Seed the Harbor corpus into the vault (Compose bind-mounts `./storage`):

```powershell
python -c "from pathlib import Path; from evaluation.datasets.controlled.load import load_harbor; load_harbor(Path('storage'))"
python scripts/rebuild_index.py
```

`rebuild_index.py` embeds with Ollama (`nomic-embed-text`). Harbor is about 10 files; the first index is slow on CPU.

6. Build images once:

```powershell
docker compose build
```

After that, `.\scripts\start_demo.ps1` (or `docker compose up --build`) is enough.

## Stop demo

```powershell
docker compose down
```

Ollama stays installed as a host service; stop it from the Ollama tray/app if you want RAM back.

## Reset demo data

The vault and SQLite index live under `storage/` (gitignored except `.gitkeep`). To wipe runtime data without touching source:

```powershell
docker compose down
Remove-Item -Recurse -Force storage\index, storage\projects, storage\documents, storage\conversations -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force storage | Out-Null
python -c "from pathlib import Path; from evaluation.datasets.controlled.load import load_harbor; load_harbor(Path('storage'))"
python scripts/rebuild_index.py
```

Do not delete `storage/.gitkeep`. Do not commit `storage/index/memoria.sqlite` or YAML records.

## Offline operation

No cloud APIs. Chat and embeddings are local Ollama HTTP (`http://127.0.0.1:11434`). Default tests use a hash embedder and HeuristicChat (`pytest` deselects `-m ollama`). Offline A/B/C scoring:

```powershell
python -c "from pathlib import Path; from evaluation.experiments.compare import run_comparison, write_report; write_report(run_comparison(Path('storage')))"
```

Live embed test (must pass, not skip, after models are pulled):

```powershell
python -m pytest -m ollama -o addopts=
```

Phase 4 retrieval is exact cosine over SQLite float32 vectors.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Launcher exits asking for `ollama pull ...` | Run the printed pull commands; `ollama list` must show `phi3:mini` and `nomic-embed-text`. |
| `docker compose` fails | Start Docker Desktop; from repo root run `docker compose ps` and `docker compose logs`. |
| `:8501` never opens | Wait for the first image build; `docker compose logs app`. |
| `:8765` never opens | `docker compose logs mcp`. MCP is Streamable HTTP at `http://127.0.0.1:8765/mcp`. |
| Empty Documents/Memory | Seed Harbor and rebuild the index (First-time setup step 5). |
| Chat is slow or Ollama 500 | Only one model should be hot; embeddings use `keep_alive: 0`. First query after a model swap can take minutes on CPU. |
| Wrong chat model | UI uses `LLM_MODEL` / Settings (`qwen2.5:3b` default). For honors demo set `LLM_MODEL=phi3:mini` in `.env` or the Compose environment. |
| Tests | Golden local suite: `python -m pytest` → 77 passed, 1 skipped, 1 deselected. |

Local processes without Docker:

```powershell
python -m mcp_server
streamlit run app/ui/streamlit_app.py
```

Compose (two services, Ollama on the host):

```powershell
docker compose up --build
```

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
