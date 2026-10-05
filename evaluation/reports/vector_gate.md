# Vector search gate

Phase 4 freeze (ADR-004).

Exact cosine over SQLite float32 blobs is the retrieval index.

`sqlite-vec` and `hnswlib` are not adopted unless a run of `evaluation.experiments.vector_gate` shows that exact cosine misses the 200 ms median latency bar on this machine. FAISS, LanceDB, Qdrant, PostgreSQL, and Redis are not in the gate.

The automated unit gate uses the Harbor corpus and the deterministic hash embedder so it does not require Ollama. Live embedding quality is a later `@pytest.mark.ollama` check.
