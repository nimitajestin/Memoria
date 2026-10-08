# Harbor system comparison

Prompts frozen at these content hashes:
- `answer.md`: `32e85f9811b9`
- `candidates.md`: `a5a80f394da2`
- `route.md`: `ae0120dcef22`
- `understand.md`: `42b423138334`

Chat: HeuristicChat (offline)

| System | Task completion | Grounded | Tool selection | Error rate | Median latency (s) |
| --- | --- | --- | --- | --- | --- |
| A | 0.00 | 0.38 | n/a | 0.00 | 0.001 |
| B | 0.50 | 0.88 | 0.92 | 0.00 | 0.237 |
| C | 0.50 | 0.88 | 0.92 | 0.00 | 0.150 |

## Item outcomes

| Item | System | Task | Route | Grounded |
| --- | --- | --- | --- | --- |
| q01 | A | False | n/a | True |
| q01 | B | False | True | True |
| q01 | C | False | True | True |
| q02 | A | False | n/a | True |
| q02 | B | False | True | True |
| q02 | C | False | True | True |
| q03 | A | False | n/a | True |
| q03 | B | False | True | True |
| q03 | C | False | True | True |
| q04 | A | False | n/a | True |
| q04 | B | False | True | True |
| q04 | C | False | True | True |
| q05 | A | False | n/a | True |
| q05 | B | False | True | True |
| q05 | C | False | True | True |
| q06 | A | False | n/a | True |
| q06 | B | False | False | False |
| q06 | C | False | False | False |
| q07 | A | False | n/a | False |
| q07 | B | True | True | True |
| q07 | C | True | True | True |
| q08 | A | False | n/a | False |
| q08 | B | True | True | True |
| q08 | C | True | True | True |
| q09 | A | False | n/a | False |
| q09 | B | False | True | True |
| q09 | C | False | True | True |
| q10 | A | False | n/a | False |
| q10 | B | True | True | True |
| q10 | C | True | True | True |
| q11 | A | False | n/a | False |
| q11 | B | True | True | True |
| q11 | C | True | True | True |
| q12 | A | False | n/a | True |
| q12 | B | False | True | False |
| q12 | C | False | True | False |
| q13 | A | False | n/a | False |
| q13 | B | True | True | True |
| q13 | C | True | True | True |
| q14 | A | False | n/a | False |
| q14 | B | True | True | True |
| q14 | C | True | True | True |
| q15 | A | False | n/a | False |
| q15 | B | True | True | True |
| q15 | C | True | True | True |
| q16 | A | False | n/a | False |
| q16 | B | True | True | True |
| q16 | C | True | True | True |
| q17 | A | False | n/a | False |
| q17 | B | False | False | False |
| q17 | C | False | False | False |
| q18 | A | False | n/a | False |
| q18 | B | True | True | True |
| q18 | C | True | True | True |
| q19 | A | False | n/a | True |
| q19 | B | True | True | True |
| q19 | C | True | True | True |
| q20 | A | False | n/a | False |
| q20 | B | False | True | True |
| q20 | C | False | True | True |
| q21 | A | False | n/a | False |
| q21 | B | True | True | True |
| q21 | C | True | True | True |
| q22 | A | False | n/a | False |
| q22 | B | False | True | True |
| q22 | C | False | True | True |
| q23 | A | False | n/a | True |
| q23 | B | True | True | True |
| q23 | C | True | True | True |
| q24 | A | False | n/a | False |
| q24 | B | False | True | True |
| q24 | C | False | True | True |

Ablation note: System A is condition A (chunks only). System B is condition E (structured, episodic, and document RAG). Rows B–D of the memory ablation are in `evaluation/reports/ablation.md`.

## Live Ollama slice (honors substitution)

ADR chat default remains `qwen2.5:3b`. This slice used Ollama chat `phi3:mini` (`LLM_MODEL=phi3:mini`). Embeddings stayed **HashEmbedder** over SQLite float32 exact cosine (ADR-004 was not changed).

**TODO:** full 24-item live A/B/C did not complete (CPU; ~4 chat calls per turn). Largest completed live slice is Harbor **q01** only:

| System | Task | Grounded | Route | Latency (s) |
| --- | --- | --- | --- | --- |
| A | False | False | n/a | 65.053 |
| B | False | False | False | 230.060 |
| C | True | False | False | 185.690 |

HeuristicChat table above is the frozen offline A/B/C result (n=24). Do not mix the live q01 row into those rates.

