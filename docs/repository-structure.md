# Repository structure

Phase 0 layout. Directories below are the target tree. Phase 0 creates this document only. Later phases add the packages as they are implemented.

`storage/` is runtime data and is gitignored except for a kept placeholder. The evaluation corpus lives under `evaluation/datasets/` so it is versioned.

```text
Memoria/
├── app/
│   └── ui/
│       ├── streamlit_app.py          # entry: navigation
│       ├── chat.py
│       ├── memory_view.py
│       ├── documents_view.py
│       └── trace_view.py
├── agent/
│   ├── graph/
│   │   └── build.py                   # StateGraph, backend switch
│   ├── state/
│   │   └── schema.py                  # typed state
│   ├── nodes/
│   │   ├── understand.py
│   │   ├── route.py
│   │   ├── retrieve.py
│   │   ├── answer.py
│   │   └── remember.py
│   ├── prompts/
│   │   ├── understand.md
│   │   ├── route.md
│   │   ├── answer.md
│   │   └── candidates.md
│   └── mcp_client.py                  # System C only
├── mcp_server/
│   ├── __main__.py                    # Streamable HTTP entry
│   ├── server.py                      # MCPServer registration
│   ├── tools/
│   │   ├── memory.py
│   │   ├── documents.py
│   │   └── project.py
│   └── resources/
│       └── knowledge.py
├── core/
│   ├── config.py
│   ├── logging.py
│   ├── safety.py                      # ids, paths, locks
│   ├── schemas/                       # pydantic models
│   ├── storage/
│   │   ├── vault.py                   # atomic YAML / JSON
│   │   ├── db.py                      # SQLite
│   │   └── memory_repo.py
│   ├── memory/
│   │   └── policy.py
│   ├── ollama.py
│   └── retrieval/
│       └── search.py
├── ingestion/
│   ├── parsers/
│   │   ├── pdf.py
│   │   ├── markdown.py
│   │   ├── text.py
│   │   ├── docx.py
│   │   └── code.py
│   ├── chunking/
│   │   └── chunk.py
│   ├── embedding/
│   │   └── batch.py
│   └── indexing/
│       └── pipeline.py
├── storage/                           # DATA_ROOT, not source
│   ├── memory/projects/{project_id}/
│   ├── documents/{project_id}/{document_id}/
│   ├── conversations/{project_id}/
│   ├── index/memoria.sqlite
│   ├── index/checkpoints.sqlite
│   └── logs/memoria.jsonl
├── evaluation/
│   ├── datasets/controlled/
│   ├── baselines/
│   │   ├── stateless_rag.py           # System A
│   │   └── direct_memory.py           # System B
│   ├── metrics/
│   ├── experiments/
│   └── reports/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── mcp/
│   ├── retrieval/
│   └── agent/
├── scripts/
│   ├── rebuild_index.py
│   └── measure_resources.py
├── docs/
│   ├── architecture.md
│   ├── repository-structure.md
│   ├── schemas.md
│   ├── mcp-interface.md
│   └── evaluation-design.md
├── docker-compose.yml                 # Phase 11
├── Dockerfile                         # Phase 11
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

## Why `core/` is extra

The brief’s tree is preserved: UI, agent, MCP server, ingestion, storage data, evaluation, and tests stay separated. `core/` is the shared implementation of schemas and durable state.

Without it, System B and the Memory view would import the MCP server package or duplicate the write rules. The agent package for System C is still forbidden from importing `core.storage` writers. A unit test in `tests/unit/` imports `agent` and fails if those writer modules are in its import closure. System B is allowed to import them because that is the non-MCP condition.

## Package roles by phase

Phase numbers are capability labels from the original brief. **Execution order** is accuracy-first (architecture ADRs unchanged):

9a Harbor dataset → 3 Ingestion → 4 Retrieval → 2 MCP → 5 Agent (A, then B, then C) → 6 Remember → 7 Import → 9b Experiment runners → 10 Reliability → 8 UI → 11 Docker → 12 Docs

| Phase | Directories it fills |
| --- | --- |
| 1 Storage | `core/schemas`, `core/storage`, `core/safety`, `core/memory/policy`, `tests/unit` |
| 9a Dataset | `evaluation/datasets/controlled`, loader tests |
| 3 Ingestion | `ingestion`, parser tests |
| 4 Retrieval | `core/ollama.py`, `core/retrieval`, `tests/retrieval` |
| 2 MCP | `mcp_server`, `tests/mcp` |
| 5 Agent | `agent`, `tests/agent` |
| 6 Memory intelligence | policy already stubbed in phase 1; phase 6 wires `remember` |
| 7 Import | `core/storage` conversation normalizers, `ingestion` import parsers |
| 9b Experiments | `evaluation/baselines`, `evaluation/metrics`, `evaluation/experiments` |
| 10 Reliability | failure tests and `scripts/rebuild_index.py` |
| 8 UI | `app/ui` |
| 11 Docker | `Dockerfile`, `docker-compose.yml` |
| 12 Docs | README completion and experiment report |

## Runtime vault

```text
storage/memory/projects/{project_id}/
  project.yaml
  status.yaml
  status.md
  decisions.md
  facts/{id}.yaml
  decisions/{id}.yaml
  goals/{id}.yaml
  knowledge/{id}.yaml
  episodes/{id}.yaml
  summaries/{id}.yaml

storage/documents/{project_id}/{document_id}/
  original.<ext>
  meta.yaml

storage/conversations/{project_id}/{conversation_id}.json
```

`status.md` and `decisions.md` are projections rewritten by `core` after a successful record change. Hand edits belong in the YAML. If a projection is hand-edited, the next successful write replaces it. The YAML file remains the record.

## Source extensions

Indexed as text: `.pdf`, `.md`, `.markdown`, `.txt`, `.docx`, `.py`, `.js`, `.jsx`, `.mjs`, `.ts`, `.tsx`, `.c`, `.h`, `.cpp`, `.hpp`, `.cc`, `.java`, `.json`, `.yaml`, `.yml`, `.toml`, `.rs`, `.go`, `.rb`, `.css`, `.html`, `.sh`, `.sql`.

Anything else is `unsupported` and is not copied into the vault.

## Import rules

| Importer | May import |
| --- | --- |
| `core` | standard library, pydantic, PyYAML, numpy, httpx |
| `ingestion` | `core` schemas and storage |
| `mcp_server` | `core`, `mcp` |
| `agent` | `core.config`, `core.schemas`, `agent.mcp_client`, langgraph |
| `app` | `agent`, `core` read/write APIs for the non-chat views |
| `evaluation.baselines.stateless_rag` | `core.retrieval`, `core.ollama` |
| `evaluation.baselines.direct_memory` | `core.retrieval`, `core.storage`, `core.memory` |

## Test layout

| Area | Proves |
| --- | --- |
| `tests/unit` | schemas, policy, chunking, path safety, atomic write |
| `tests/mcp` | every tool and resource, including refusal cases, via in-process `Client` |
| `tests/integration` | index a fixture, restart the SQLite connection, read it back |
| `tests/retrieval` | known queries against the controlled corpus; Ollama marked optional |
| `tests/agent` | graph routing with a fake MCP client and a fake chat model |

Tests that need a live Ollama use `@pytest.mark.ollama` and are skipped by default.

## Config files introduced with implementation

`.env.example` lists every variable in the architecture configuration table. `.gitignore` ignores `.env`, `storage/**` contents, `__pycache__`, and virtualenvs, and keeps `storage/.gitkeep`.

Phase 0 does not add those files. Phase 1 adds `.gitignore`, `pyproject.toml`, and the storage package together so the ignore rules land with the first writable vault.
