# MCP interface specification

One server. Name: `memoria`. SDK: official MCP Python SDK v2. Protocol revision: 2026-07-28.

The server exposes tools and resources. It does not expose prompts. It does not call Ollama’s chat API. Indexing may call the embedding API through `core`, because embedding is part of document indexing rather than agent planning.

## Transport

| Mode | Use |
| --- | --- |
| Streamable HTTP `http://<host>:8765/mcp` | Docker and the local two-process run |
| In-process `Client(server)` | Automated tests |
| stdio | Optional debug launch only |

`mcp.run(transport="streamable-http", host=..., port=8765)` is the process entry. SSE is not enabled.

Tool names use dots, which the 2026-07-28 specification allows (`admin.tools.list` is a spec example). Python functions keep underscore names and register the public name explicitly, for example `@mcp.tool(name="memory.search")`. Phase 2 confirms the installed SDK accepts that override. If it does not, the server registers `memory_search` and the client maps the public name. The evaluation logs the public name either way.

Resource URIs:

| URI | Body |
| --- | --- |
| `project://{project_id}/status` | Status projection markdown |
| `project://{project_id}/decisions` | Decisions projection markdown |
| `project://{project_id}/knowledge` | Active knowledge records as Markdown |
| `project://{project_id}/memory` | Catalog of active records: id, type, topic or title, updated_at. Not full bodies. |
| `document://{document_id}` | Document metadata plus chunk locations, without embedding blobs |
| `conversation://{conversation_id}` | Normalized transcript JSON |

Templates use single path segments. The SDK’s path checks apply. `project_id` and ids are validated again inside the handler.

Resources are read-only. Tools perform actions.

## Response envelope

Every tool returns a JSON object as text content.

Success:

```json
{
  "ok": true,
  "data": {}
}
```

Expected failure:

```json
{
  "ok": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "No memory record with that id is in this project.",
    "details": {}
  }
}
```

| Code | When |
| --- | --- |
| `VALIDATION` | Schema, type, or range failure |
| `NOT_FOUND` | Unknown project, memory, document, or conversation |
| `CONFLICT` | Duplicate create, revision mismatch, or policy conflict that blocks the write |
| `FORBIDDEN` | Path escape, bad id characters, symlink escape, project boundary violation |
| `UNSUPPORTED` | File type or import format outside the allowlist |
| `FAILED_DEPENDENCY` | Embedding model or SQLite rebuild prerequisite missing |
| `INTERNAL` | Unexpected exception after the store was left unchanged |

Transport failure (connection refused, timeout) is an exception in the client, not an envelope. The agent maps it to a user-visible MCP-unavailable error.

Handlers catch storage exceptions and return `INTERNAL` only after rolling back the transaction or discarding the temp file.

## Shared arguments

`project_id` is required on every tool except `documents.get` and `memory.get`, which still check that the record’s project matches when `project_id` is supplied. Callers in this application always send `project_id`.

Limits:

| Argument | Default | Maximum |
| --- | --- | --- |
| `limit` on searches | 5 | 5 |
| `query` length |  | 1000 characters |
| record body fields |  | 8000 characters |

## Memory tools

### `memory.search`

Read-only.

Arguments: `project_id`, `query`, `types` (optional list), `limit`.

Behavior: case-insensitive match over topic, title, statement, decision, summary, and tags in the project’s active records, then a bounded embedding search over those same records if the embedding model is available. The lexical pass always runs, so search still works when Ollama is down; the result notes `semantic: false`.

Returns: list of `{id, type, title_or_topic, score, snippet, updated_at}`. Snippets are at most 400 characters. Full bodies are fetched with `memory.get`.

### `memory.get`

Arguments: `project_id`, `id`.

Returns the record. `NOT_FOUND` when the id is absent or belongs to another project.

### `memory.create`

Arguments: `project_id`, `record` (object matching the schema for its type, without `id` and `revision`), `expected_duplicate_behavior`.

The server assigns `id` and `revision: 1`, runs schema validation, then runs the same duplicate and conflict checks as the policy. On duplicate it returns `CONFLICT` and does not write. Decisions cannot be created with `status: superseded`.

Returns the stored record.

### `memory.update`

Arguments: `project_id`, `id`, `patch`, `expected_revision`.

`patch` may change content fields and, for goals, `goal_status`. It may not change `id`, `type`, `project_id`, or `created_at`.

When `expected_revision` does not match, the tool returns `CONFLICT` and the file is untouched.

For `type: decision`, update of the decision text is rejected with `VALIDATION`. Callers create a new decision with `supersedes`. Status may move from `active` to `withdrawn` only when the caller sets `status` and the revision matches. Moving to `superseded` is reserved for the create path that links the successor.

### `memory.delete`

Arguments: `project_id`, `id`, `expected_revision`.

Decisions and status are soft-deleted: `status` becomes `withdrawn`, the file remains. Other types are removed from disk and from `memory_index` when the revision matches. A revision mismatch returns `CONFLICT` and deletes nothing.

## Document tools

### `documents.search`

Arguments: `project_id`, `query`, `limit`, optional `file_type`, optional `document_id`.

Embeds `query`, runs exact cosine within the project, applies the optional filters, and returns evidence items as specified in `docs/schemas.md`. An empty index returns `ok: true` and an empty list. A missing embedding model returns `FAILED_DEPENDENCY`.

### `documents.get`

Arguments: `project_id`, `document_id`.

Returns metadata and the list of chunk locations. Chunk text is included only when `include_text` is true, and then at most 20 chunks. The agent uses search for text. The UI uses this for the document page.

### `documents.list`

Arguments: `project_id`.

Returns id, filename, file type, status, chunk count, indexed time, and error string for each document.

### `documents.reindex`

Arguments: `project_id`, optional `document_id`, `force` (default false).

Without `document_id`, hashes every vault file and embeds only changed documents. With `force: true`, re-embeds the selected document or the whole project. Returns counts: `unchanged`, `reindexed`, `failed`, plus per-file errors.

This tool is for the user and for tests. The agent graph does not call it during a question.

Indexing a new upload is a `core` pipeline invoked by the Documents view, which copies the file into the vault and then calls the same function `documents.reindex` uses. The agent is not given a path-writing tool.

## Project tools

### `project.get_status`

Arguments: `project_id`.

Returns the status record plus the Markdown projection.

### `project.update_status`

Arguments: `project_id`, `summary`, `phase`, `blockers`, `expected_revision`.

Updates the single status record under the revision rule. Regenerates `status.md`.

## Annotations

| Tool | Read only | Destructive |
| --- | --- | --- |
| `memory.search`, `memory.get` | yes | no |
| `memory.create`, `memory.update` | no | no |
| `memory.delete` | no | yes |
| `documents.search`, `documents.get`, `documents.list` | yes | no |
| `documents.reindex` | no | no |
| `project.get_status` | yes | no |
| `project.update_status` | no | no |

All tools set a closed-world annotation: they operate on this vault, not on the public web.

## Client contract used by the agent

Per turn the retriever may call:

- `memory.search` and then `memory.get` for the chosen ids, and/or
- `documents.search`

The remember node may call `memory.create` or `memory.update` at most once.

It does not call delete, reindex, or project update. Those exist for the UI, tests, and reliability work.

The client records name, argument keys (not full document text), latency, `ok`, and `error.code` into `tool_trace`.

## Tests required in Phase 2

For each tool: one valid call, one invalid payload, one unknown project.

Additional cases, mapped to tools:

| Case | Expected |
| --- | --- |
| Missing memory id | `NOT_FOUND` |
| Duplicate fact create | `CONFLICT`, one file on disk |
| Decision text update | `VALIDATION`, original file hash unchanged |
| Revision mismatch | `CONFLICT`, hash unchanged |
| Malformed YAML already on disk | `memory.get` returns `INTERNAL` or a dedicated details code `MALFORMED`, and does not rewrite the file |
| Missing document | `NOT_FOUND` |
| Unsupported upload handed to reindex | `UNSUPPORTED` or a file status of `unsupported` |
| Empty file | status `empty`, search omits it |
| Repeated search | same ids, no duplicate rows |
| Project id `../other` | `FORBIDDEN` |
| Document id containing a path separator | `VALIDATION` |
| Embedding call failing during reindex | document status `failed`, previous chunks for other documents remain |
| Second concurrent update of one record | one success, one `CONFLICT` |

Resource tests read each URI template with a known id and assert a missing id is a protocol-level not-found rather than a stack trace.

Phase 10 adds corrupt-file, huge-file, and MCP-process-down tests. The interface above is what those tests call.
