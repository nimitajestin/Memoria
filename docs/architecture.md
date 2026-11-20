# Memoria architecture

This document is the architecture of the system in this repository. It was written before the packages existed and it is still the contract: who owns which component, how one turn moves, and the decisions in the ADR table. The git history is the build order. It is not a second design.

One measurement on this machine changed the chat generation budget. A 4096-token context that changed between nodes reloaded the model on every step. The bounds table records the replacement. The component boundaries did not change.

## Research question

Primary: does exposing persistent structured project memory through one custom MCP server improve effectiveness, consistency, grounding, and task completion of a resource-constrained local RAG agent, compared with stateless RAG?

Secondary: can useful persistent agentic memory run on an 8 GB RAM, CPU-only machine with no cloud services?

The system is the smallest design that can answer those questions with a controlled comparison. Feature count is not a goal.

## What this system is

A single user, on one machine, works in one project at a time.

1. The Streamlit UI collects a question, shows the answer, and shows an operational trace.
2. A LangGraph agent decides whether the question needs memory, documents, both, or neither.
3. In the research system, that decision is carried out by an MCP client talking to one custom MCP server.
4. The MCP server reads and writes human-readable project memory and a local document index.
5. Ollama, running on the host, supplies the chat model and the embedding model.

The MCP server is a reliable knowledge service. It does not plan, browse, or call the LLM. The agent decides when to call it, and the call budget is finite.

## Hardware budget

Target machine: about 8 GB system RAM, Intel integrated graphics, no discrete GPU, hundreds of gigabytes of free disk.

The running set is:

| Resident | Budget |
| --- | --- |
| Operating system and browser | left untouched by the app |
| Ollama chat model | one small model, default `qwen2.5:3b` |
| Ollama embedding model | loaded only during embedding batches, then unloaded |
| App process (Streamlit + agent) | one Python process |
| MCP process | one Python process |
| Document corpus, chunk text, embeddings | on disk in SQLite and files |

The chat model and the embedding model are not kept resident together. After an embedding batch the client sends Ollama `keep_alive: 0` for the embedding model. Chat context is capped so the KV cache stays small.

Ingestion is incremental: identify the file, parse one unit, chunk it, embed a small batch, commit, release the batch, continue. A query loads only the top-k chunk texts.

## Frozen decisions

These are closed. A later phase may replace a decision only when a measurement on this machine falsifies the assumption recorded here. The replacement is written into `docs/evaluation-design.md` results, not made silently.

| ID | Decision |
| --- | --- |
| ADR-001 | Python 3.11 or newer. One repository. `pyproject.toml` is the dependency source. `requirements.txt` is generated from it for Docker and graders. |
| ADR-002 | MCP Python SDK v2 (`mcp>=2,<3`), protocol revision 2026-07-28. Production transport is Streamable HTTP. Tests use the SDK in-process client. SSE is unused. |
| ADR-003 | Shared library `core/` owns schemas, files, SQLite, validation, and retrieval. The MCP server is a thin adapter. The agent in the MCP condition imports the MCP client, not storage writers. |
| ADR-004 | Default vector search is exact cosine over float32 blobs in the same SQLite file as metadata. No vector-database service. Phase 4 runs the benchmark gate in the evaluation design before any other index is adopted. |
| ADR-005 | Ollama over HTTP with `httpx`. Chat default `qwen2.5:3b`. Embedding default `nomic-embed-text` (768 dimensions). Both names come from configuration. Embedding endpoint is `POST /api/embed`. |
| ADR-006 | One LangGraph `StateGraph`. Explicit nodes, no ReAct loop. Checkpoints in SQLite via `langgraph-checkpoint-sqlite`. |
| ADR-007 | YAML records are the memory source of truth. Markdown files under the project are generated views. SQLite indexes metadata and document chunks. |
| ADR-008 | A deterministic policy decides reject, update, or create. The model may only propose candidates. |
| ADR-009 | Streamlit is the only UI. Four views: Chat, Memory, Documents, Trace. |
| ADR-010 | Docker Compose runs two services from one image: `app` and `mcp`. Ollama stays on the host. |
| ADR-011 | Retrieval score is cosine similarity. No cross-encoder reranker. |
| ADR-012 | The three experimental systems share the index, the embedder, the answer instructions, and the model settings. They differ only in how context is acquired. |

### Why these defaults

`qwen2.5:3b` is the default chat model because public CPU-only measurements put it near 2 GB on disk and roughly 3–4.5 GB resident, with working tool-style structured output. A 7B model is outside the default budget on 8 GB once the OS, browser, and two Python processes are counted. `nomic-embed-text` is the default embedder because it is a small English embedding model distributed for Ollama (about 274 MB) and is large enough for a controlled corpus. `all-minilm` is the documented fallback if embedding RAM or latency is too high.

Exact SQLite search is the default because the evaluation corpus is small, exact search is the quality ceiling, and it adds no native extension and no extra process. `sqlite-vec` remains pre-1.0. `hnswlib` and FAISS keep indexes in RAM. They are benchmark candidates, not the architecture.

Streamable HTTP is the Docker boundary: the app container opens `http://mcp:8765/mcp`. The official SDK accepts that URL in `Client`. In-process `Client(server)` is reserved for tests so tool tests do not need a port. stdio remains available for a local single-process debug run and is not the comparison condition.

`httpx` talks to Ollama directly so tests can fake the HTTP API without the `ollama` package.

## Process model

```text
Browser
  → Streamlit (app process)
      → LangGraph agent
          → MCP client  ---- Streamable HTTP ----  MCP server (second process)
                                                        → core.storage
                                                        → storage/  (volume)
      → Ollama on the host (chat and embeddings)
```

Local development without Docker uses the same two processes and the same URL, with Ollama at `http://127.0.0.1:11434`.

The UI reads the vault for the Memory and Documents screens so a person can inspect the same files they can open in an editor. Chat mutations go through the agent and then MCP. Forms that edit memory call the same `core` functions the MCP tools call, so validation stays in one place. The experimental MCP condition does not use those direct calls inside the agent.

One uvicorn worker serves MCP. LangGraph’s SQLite checkpointer is documented for lightweight single-user use; the app holds one lock around a turn. That matches a single local user.

## Component boundaries

| Component | Owns | Must not |
| --- | --- | --- |
| `app/ui` | Pages, uploads, display of trace and evidence | Choose tools, write memory except through `core` validators, call Ollama for answers |
| `agent` | Task routing, MCP calls, answer assembly, memory proposals | Parse arbitrary paths, embed the corpus, be the source of truth |
| `mcp_server` | Tool and resource registration, protocol errors | Plan, loop, call the chat model |
| `core` | Schemas, atomic IO, SQLite, chunking, retrieval, memory policy, Ollama HTTP | MCP protocol types, Streamlit |
| `ingestion` | Parsers and chunkers used by `core` indexing | Serve requests |
| `evaluation` | Systems A and B, dataset, metrics | Change production tool semantics |
| `storage/` | Runtime data only | Source code |

System A and System B live under `evaluation/baselines/` and are allowed to call `core` retrieval and, for System B, `core` memory. System C is the production agent path.

## Agent graph

One turn is one bounded walk. There is no edge back to routing.

```text
START
  → understand
  → route
  → retrieve          (none, memory, documents, or both)
  → answer
  → remember          (policy, then at most one MCP write)
  → END
```

`understand` rewrites the user text into a short task string and a project-scoped search query. It does not call MCP. A question of at most 200 characters with no prior turns is already that query, so the node does not call the model.

`route` emits exactly one label: `none`, `memory`, `documents`, or `both`, plus an operational reason of at most 200 characters. The reason is shown in the trace. Hidden chain-of-thought is not requested, stored, or displayed.

`retrieve` performs the calls for that label and stops.

`answer` sees only the bounded state: task, selected memories, selected chunks, and the latest user message. It must attach grounding and evidence ids drawn from that state.

`remember` asks for at most two memory candidates, then runs the deterministic policy. A create or update is one MCP call. A reject writes nothing. A message that is only a question does not propose a memory, so the node does not call the model.

Failure at any node goes to `fail`, which sets a user-visible error and ends the turn. One tool retry is allowed and counts toward the tool cap.

### Bounds

| Bound | Value |
| --- | --- |
| MCP tool calls per turn | 4 |
| Memories returned | 5 |
| Chunks returned | 5 |
| Evidence characters placed in the answer prompt | 6000 |
| Chat `num_ctx` | 1024 for every node, so the model stays loaded |
| Chat `num_predict` | 80 understand, 64 route, 80 answer, 96 remember |
| Chat `keep_alive` | 10 minutes |
| Embedding batch | 8 chunks |
| Chunk target / max / overlap | 800 / 1200 / 100 characters |
| Chunks stored per document | 500, then status `truncated` |
| Upload size | 20 MB |
| Active facts per project | 200 |
| Active decisions per project | 100 |
| Active records of each other type | 200 |
| Candidate memories proposed per turn | 2 |

State holds ids, scores, short text, and the trace. It does not hold the corpus or the full checkpoint history of other threads. Conversation display history in the UI is separate from persistent memory and is capped at the last 20 turns sent as background, with older turns available only as stored conversation files.

### Grounding

Every answer carries one primary label:

| Label | Meaning |
| --- | --- |
| `known_from_memory` | Claim is backed by a retrieved memory id |
| `known_from_documents` | Claim is backed by a retrieved chunk id |
| `user_provided` | Claim restates the current user message |
| `model_inference` | Conclusion drawn from retrieved evidence, labeled as inference |
| `unknown` | The store did not contain enough evidence |
| `conflict` | Retrieved records disagree; both sides are shown |

A post-check drops any evidence id that was not actually retrieved and downgrades the label to `unknown` if nothing valid remains. The model cannot invent a citation by naming a plausible id.

When two retrieved items conflict, the answer surfaces both. Preference order for a suggested reading, which is shown as a preference and not a silent rewrite:

1. Newer `updated_at` within the same authority class.
2. Authority: decision, then fact, then knowledge, then document chunk, then episode, then conversation summary.

An existing decision is never overwritten in place. A revision is a new record. The previous record stays on disk.

## Memory lifecycle

The model proposes. `core.memory.policy` disposes.

For each candidate:

1. Reject when confidence is below 0.6.
2. Reject when the candidate is not marked stable, project-specific, and useful in a later session.
3. Reject a fact or decision that cites no retrieved evidence id or explicit user statement.
4. Reject when the normalized content hash matches an active record of the same type.
5. If the same type and topic already exist and the content differs, flag `conflict`. Decisions are not overwritten. Facts keep both records and link `conflicts_with`.
6. Otherwise create.
7. Status and goals update in place only when `expected_revision` matches. A mismatch returns `CONFLICT` and leaves the file unchanged.
8. Reject when the active-record cap for that type is full.

Outcomes recorded on the trace: `reject`, `update`, `create`. Deletes requested by the model during a turn are not part of this path. Deletion is a separate tool used from tests and the Memory view.

Conversation text is stored as a normalized transcript. A summary may become a `conversation_summary` record only through the same policy. Raw turns are not copied into the memory tree.

## Ingestion

Supported types: PDF, Markdown, TXT, DOCX, and source text (Python, JavaScript, TypeScript, C, C++, Java, plus other plain-text extensions listed in the repository structure).

Pipeline for one file:

1. Reject the path unless it resolves inside the project vault.
2. Hash the bytes.
3. If the hash matches the indexed document, stop.
4. Parse to units (page, heading section, or code block).
5. Chunk from those units.
6. Embed and commit in batches of 8.
7. Delete chunks that belonged to the previous hash of that document.
8. Drop parser objects before the next file.

A changed document re-embeds only that document. A deleted document removes its vault file, its chunk rows, and its embedding rows in one transaction.

Parsers: `pypdf` for PDF text, `python-docx` for DOCX, the standard library for Markdown, TXT, and source. Scanned PDFs without a text layer become a failed document with a clear error. OCR is out of scope.

Code chunking uses regular expressions for top-level functions and classes. A full language parser is not required for the first measured version.

## Retrieval

1. Prepare the search string from the route node.
2. Embed that string.
3. Cosine against vectors for the current project only, reading blobs in batches from SQLite.
4. Keep the top 5.
5. Return source, document id, chunk id, location, score, and text.

Metadata filters are equality filters the tools already accept (`file_type`, `document_id`). They are optional.

No second-stage neural reranker. Phase 4 may record a lexical tie-break only if exact cosine ties are frequent in the dataset and the tie-break moves Recall@5. Until that measurement, score is cosine alone.

## Resource measurement

Each indexing run and each query records:

- process RSS at start and end (`psutil`)
- peak RSS sampled during the operation
- wall time
- embedding time and search time separately
- vault size on disk

Logs are JSON lines. They include request id, execution id, tool name, latency, result counts, and error codes. They omit document text and memory bodies.

## Failure behavior

| Condition | Behavior |
| --- | --- |
| Ollama down | Turn ends with an error that names the chat or embedding call. Memory is unchanged. |
| MCP down | System C returns an MCP-unavailable error. It does not fall through to direct disk writes. |
| Embedding model missing | Indexing stops on that batch and marks the document `failed`. Prior documents stay committed. |
| Corrupt PDF or DOCX | That file is `failed`. The batch continues. |
| Malformed YAML | The indexer skips the file and reports it. Writers refuse to replace a valid file with a schema-invalid payload. |
| Bad project id or path escape | `FORBIDDEN` or `VALIDATION`. No IO outside the vault. |
| SQLite index missing or unreadable | Document text files remain. A rebuild walks the vault hashes and re-embeds. |
| Empty file | Document row with status `empty` and zero chunks. |
| Duplicate memory create | `CONFLICT` or policy `reject`. The existing file stays. |

Writes use a temp file in the same directory, then `os.replace`. SQLite uses WAL. Memory writes take a per-project file lock so a UI edit and an MCP write cannot interleave a record.

## Security

- `DATA_ROOT` is the only root for reads and writes performed by tools.
- Project ids match `^[a-z0-9][a-z0-9_-]{0,63}$`.
- Stored filenames are a safe basename. User paths are not reused as vault paths.
- Resolved paths must stay under `storage/documents/{project_id}` or `storage/memory/projects/{project_id}`.
- Symlinks that resolve outside the vault are rejected.
- YAML is loaded with the safe loader.
- Source files are indexed as text and never executed.
- The model never receives a general filesystem tool.

## Configuration

Environment variables, with defaults:

| Variable | Default |
| --- | --- |
| `DATA_ROOT` | `./storage` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |
| `LLM_MODEL` | `qwen2.5:3b` |
| `EMBEDDING_MODEL` | `nomic-embed-text` |
| `MCP_URL` | `http://127.0.0.1:8765/mcp` |
| `MCP_HOST` | `127.0.0.1` (`0.0.0.0` inside the MCP container) |
| `MCP_PORT` | `8765` |
| `LOG_LEVEL` | `INFO` |

Docker sets `OLLAMA_BASE_URL` to `http://host.docker.internal:11434` and `MCP_URL` to `http://mcp:8765/mcp`.

## Deployment shape

One image. Two Compose services.

- `mcp` runs `python -m mcp_server`, publishes `127.0.0.1:8765:8765`, mounts `./storage`.
- `app` runs Streamlit on `127.0.0.1:8501`, mounts the same `./storage`, depends on `mcp`.

Ollama is installed on the host and is not a Compose service. After the models are pulled and the Python packages are installed, the core path does not call the network except the local Ollama port and the local MCP port.

## Observability trace

The Trace view renders this sequence from structured state, omitting any step that did not run:

```text
Task understood
→ Routed to memory | documents | both | none
→ MCP tools called (name, ok, latency)
→ N memories retrieved
→ N chunks retrieved
→ Answer generated (grounding label)
→ Memory create | update | reject | not proposed
```

## Out of scope

Multi-agent layouts, voice, mobile, authentication, SaaS, cloud LLMs, cloud embeddings, web search, autonomous browsing, fine-tuning, custom foundation models, Kubernetes, a separate frontend framework, Redis, PostgreSQL, Qdrant, OCR, a neural reranker, and extra MCP tools beyond the interface spec.

LangGraph’s long-term store is not used. Project memory is the YAML vault. Checkpoints are only short-term turn state.

## Documentation baseline

Checked 5 October 2026:

- MCP Python SDK v2: [py.sdk.modelcontextprotocol.io/v2](https://py.sdk.modelcontextprotocol.io/v2/)
- MCP tools and dotted names: [specification 2026-07-28 tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- MCP client and Streamable HTTP: [client](https://py.sdk.modelcontextprotocol.io/v2/client/), [transports](https://py.sdk.modelcontextprotocol.io/v2/client/transports/)
- MCP server run: [running the server](https://py.sdk.modelcontextprotocol.io/v2/run/)
- LangGraph checkpoints and SQLite saver: [checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers), `langgraph.checkpoint.sqlite.SqliteSaver`
- Ollama embeddings: [docs.ollama.com/api/embed](https://docs.ollama.com/api/embed)
- Streamlit current stable line at inspection: 1.64
- PDF text: `pypdf`

## Phase 0 exit

Phase 0 is complete when this set exists and implementation has not started:

- `docs/architecture.md`
- `docs/repository-structure.md`
- `docs/schemas.md`
- `docs/mcp-interface.md`
- `docs/evaluation-design.md`

Phase 1 may create the packages, schemas, and memory CRUD described in those documents. It may not start the MCP server, parsers, or agent.
