# Data schemas

Phase 0 contract for files and SQLite. Phase 1 implements these models and the CRUD operations. Field names here are authoritative.

Identifiers are lowercase prefixes plus 12 hex characters from UUID4, for example `decision_a1b2c3d4e5f6`. Timestamps are ISO-8601 UTC. Hashes are SHA-256 hex of the exact bytes or of the normalized UTF-8 text, as specified per object.

## Project file

`storage/memory/projects/{project_id}/project.yaml`

```yaml
id: project_harbor
name: Harbor
description: Controlled project used by the local copilot.
created_at: "2026-10-05T00:00:00Z"
updated_at: "2026-10-05T00:00:00Z"
```

`id` equals the directory name and matches `^[a-z0-9][a-z0-9_-]{0,63}$`.

## Common record fields

Every record file includes:

| Field | Rule |
| --- | --- |
| `id` | Stable id. Prefix matches `type`. |
| `type` | `fact`, `decision`, `goal`, `knowledge`, `episode`, `conversation_summary`, `status` |
| `project_id` | Owning project. |
| `created_at`, `updated_at` | UTC timestamps. |
| `status` | `active`, `superseded`, `withdrawn` |
| `revision` | Integer, starts at 1. Increments on update. |
| `confidence` | Number from 0 to 1, or null when a person wrote the record. |
| `source` | Provenance object below. |
| `supersedes` | Id or null. |
| `conflicts_with` | List of ids. |
| `created_by` | `user`, `agent`, or `import` |
| `execution_id` | Agent execution id, or null. |

`source`:

```yaml
source:
  kind: user          # user | document | conversation | agent | import
  ref: null           # document id, chunk id, or conversation id
  quote: null         # at most 240 characters, copied from the cited text
```

Writers reject a record whose `quote` is not a substring of the cited chunk or user turn when `ref` is present. This is the citation check for memory, parallel to the answer post-check.

## Type-specific fields

### Fact — `facts/{id}.yaml`

```yaml
type: fact
topic: hardware
statement: The development machine has 8 GB of RAM and no discrete GPU.
```

### Decision — `decisions/{id}.yaml`

```yaml
type: decision
topic: vector_storage
decision: Use exact cosine search over float32 vectors stored in SQLite.
reason: The corpus is small and the machine has no spare RAM for an in-memory ANN index.
status: active
```

Decisions change by inserting a new file whose `supersedes` points at the previous id, then setting the previous file’s `status` to `superseded` in the same locked operation. The previous body is kept.

### Goal — `goals/{id}.yaml`

```yaml
type: goal
statement: Compare stateless RAG with MCP-backed memory on the controlled set.
goal_status: open        # open | done | dropped
```

### Knowledge — `knowledge/{id}.yaml`

```yaml
type: knowledge
title: Retrieval preference
body: When a decision and a note disagree, show both and prefer the decision if it is newer.
tags: [retrieval, grounding]
```

### Episode — `episodes/{id}.yaml`

```yaml
type: episode
occurred_at: "2026-10-05T00:00:00Z"
summary: The architecture freeze selected SQLite exact search.
```

### Conversation summary — `summaries/{id}.yaml`

```yaml
type: conversation_summary
conversation_id: conv_0123456789ab
summary: The user confirmed that Ollama stays on the host.
```

### Status — `status.yaml` (one file)

```yaml
type: status
id: status_project_harbor
phase: architecture
summary: Phase 0 specification is frozen.
blockers: []
```

There is one status record per project. Updates require `expected_revision`.

## Projections

`status.md` and `decisions.md` are generated Markdown. They include the record id, status, timestamp, and body fields so a person can read them without parsing YAML. They are not parsed back into records.

## Memory candidate

The agent proposes this object. It is not stored unless the policy returns `create` or `update`.

```yaml
type: fact
topic: hardware
statement: The target machine has 8 GB of RAM.
confidence: 0.86
stable: true
project_specific: true
future_useful: true
evidence_refs: [chunk_0123456789ab]
source_kind: document
```

Policy results:

```yaml
outcome: reject          # reject | update | create
reason: duplicate        # low_confidence | not_durable | unsupported | duplicate | conflict | capacity | revision_mismatch | accepted
target_id: fact_0123456789ab
conflict_ids: []
```

## Conversation file

`storage/conversations/{project_id}/{conversation_id}.json`

```json
{
  "id": "conv_0123456789ab",
  "project_id": "project_harbor",
  "source": "import",
  "origin_format": "markdown",
  "created_at": "2026-10-05T00:00:00Z",
  "title": "Import of planning chat",
  "turns": [
    {
      "role": "user",
      "content": "We should keep Ollama on the host.",
      "timestamp": null
    }
  ]
}
```

`role` is `user`, `assistant`, or `system`. Import parsers accept JSON (a list of role/content objects or this normalized shape), Markdown transcripts with `User:` / `Assistant:` labels, and plain TXT with the same labels. Unparseable files fail the import and write nothing.

Raw transcripts are not memory records.

## Document metadata

`storage/documents/{project_id}/{document_id}/meta.yaml`

```yaml
id: doc_0123456789ab
project_id: project_harbor
filename: notes.md
file_type: markdown
byte_size: 1200
content_hash: "<sha256 of original bytes>"
indexed_at: "2026-10-05T00:00:00Z"
status: indexed          # pending | indexed | empty | failed | truncated | unsupported
error: null
chunk_count: 3
```

The original bytes sit beside this file as `original` plus the allowlisted extension.

## Chunk

Stored in SQLite, not as one file per chunk.

| Field | Meaning |
| --- | --- |
| `id` | `chunk_` + 12 hex chars |
| `document_id` | Parent document |
| `project_id` | Denormalized for project-scoped search |
| `chunk_index` | Order within the document |
| `section` | Heading, function name, or null |
| `page` | 1-based PDF page, else null |
| `line_start`, `line_end` | 1-based lines for text and code, else null |
| `content_hash` | SHA-256 of the chunk text |
| `char_count` | Length of `text` |
| `text` | The chunk body |
| `created_at` | Index time |

## Embedding

| Field | Meaning |
| --- | --- |
| `chunk_id` | Primary key |
| `model` | Embedding model name used |
| `dimension` | Integer, 768 for the default model |
| `vector` | Little-endian float32 blob, length `dimension * 4` |
| `created_at` | Index time |

A database refuses a vector whose dimension differs from the dimension stored in `index_meta` for that model. Rebuilding with a new embedding model is an explicit rebuild, which deletes embedding rows and fills them again.

## SQLite

File: `storage/index/memoria.sqlite`. WAL mode. Foreign keys on.

```sql
CREATE TABLE index_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  file_type TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  indexed_at TEXT,
  vault_relpath TEXT NOT NULL
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  section TEXT,
  page INTEGER,
  line_start INTEGER,
  line_end INTEGER,
  content_hash TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE embeddings (
  chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dimension INTEGER NOT NULL,
  vector BLOB NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE memory_index (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  topic TEXT,
  revision INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  vault_relpath TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_chunks_project ON chunks(project_id);
CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_memory_project_type ON memory_index(project_id, type, status);
```

`index_meta` holds `embedding_model`, `embedding_dimension`, and `schema_version`. `schema_version` starts at `1`.

`memory_index.content_hash` is the hash of the canonical YAML. On read, if the file hash differs, the repository reloads and updates the index row before returning the record. If the file fails schema validation, the read returns an error for that id and does not replace the previous index row.

Checkpoints use a different file, `storage/index/checkpoints.sqlite`, owned by LangGraph’s `SqliteSaver`. Application code does not write that schema.

## Agent state

Persisted by the checkpointer for the thread. JSON-serializable.

| Field | Content |
| --- | --- |
| `request_id`, `execution_id` | Ids for logs |
| `project_id`, `thread_id` | Scope |
| `user_query` | Current message |
| `task` | Short task string |
| `search_query` | String actually embedded |
| `route` | `none`, `memory`, `documents`, `both` |
| `route_reason` | At most 200 characters |
| `memories` | At most 5 records, bodies included |
| `evidence` | At most 5 chunks with scores and locations |
| `tool_trace` | `{name, latency_ms, ok, error_code}` per call |
| `answer` | Final text |
| `grounding` | Label from the architecture doc |
| `citations` | Ids that survived the post-check |
| `memory_candidates` | At most 2 |
| `memory_actions` | Policy outcomes |
| `error` | Null or `{code, message}` |

## Evidence item

```yaml
source: document
document_id: doc_0123456789ab
chunk_id: chunk_0123456789ab
location:
  filename: notes.md
  section: Retrieval
  page: null
  line_start: 10
  line_end: 24
retrieval_score: 0.81
retrieved_at: "2026-10-05T00:00:00Z"
text: "..."
```

Memory hits use the same shape with `source: memory`, `memory_id` set, and `chunk_id` null.

## Canonical YAML

Records are written with UTF-8, `\n` newlines, keys in the field order of the pydantic model, and no sort-by-key reordering beyond that model order. Comparison hashes use this canonical form.
