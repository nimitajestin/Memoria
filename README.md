# Memoria

Local-first agentic knowledge copilot with one custom MCP memory server, aimed at an 8 GB RAM, CPU-only machine.

Phase 0 is the architecture freeze. Application code is not implemented yet.

## Specification

- [Architecture](docs/architecture.md)
- [Repository structure](docs/repository-structure.md)
- [Data schemas](docs/schemas.md)
- [MCP interface](docs/mcp-interface.md)
- [Evaluation design](docs/evaluation-design.md)

The research question is whether structured project memory, exposed through a single MCP server, improves a local RAG agent compared with stateless RAG, under a hard RAM budget and with no cloud APIs.

## Status

| Phase | State |
| --- | --- |
| 0 Architecture | Frozen in `docs/` |
| 1 Storage and later | Not started |
