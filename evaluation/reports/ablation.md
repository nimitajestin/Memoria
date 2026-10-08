# Harbor memory ablation

System B call path only. Prompts frozen:
- `answer.md`: `32e85f9811b9`
- `candidates.md`: `a5a80f394da2`
- `route.md`: `ae0120dcef22`
- `understand.md`: `42b423138334`

Chat/embed: HeuristicChat + HashEmbedder (offline).

| Condition | What it may read | Task completion | Grounded | Median latency (s) | Flipped vs previous |
| --- | --- | --- | --- | --- | --- |
| A | No persistent memory. Same as System A. | 0.00 | 0.38 | 0.001 | n/a |
| B | Raw conversation turns only. | 0.17 | 0.62 | 0.135 | +['q07', 'q10', 'q18', 'q24'] -[] |
| C | Structured records only; no episodes or documents. | 0.38 | 0.54 | 0.246 | +['q08', 'q13', 'q14', 'q15', 'q16', 'q19', 'q21'] -['q07', 'q24'] |
| D | Structured plus episodic memory; no document RAG. | 0.50 | 0.67 | 0.239 | +['q07', 'q11', 'q23'] -[] |
| E | Structured, episodic, and document RAG. Full System B. | 0.50 | 0.88 | 0.211 | none |

## Interpretation

- **A.** Chunks-only baseline: no stored Harbor decisions or facts.
- **B.** Transcript overlap can surface import asides but not structured decisions.
- **C.** Structured memory is the first condition that can answer seeded decision/fact items.
- **D.** Episodes add narrative context; Harbor gold is mostly structured, so gains are small.
- **E.** Adding document RAG recovers corpus-only items that memory cannot answer.

