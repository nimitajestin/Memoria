# Research and evaluation design

Phase 0 design for the comparison, the ablation, the dataset, and the resource logs. Phase 9 implements the runners. No numbers are claimed here.

## Question the experiments answer

Does System C (structured memory reached through the custom MCP server) improve cross-session recall, consistency, grounding, and task completion relative to System A (stateless RAG), on one fixed model, one index, and one small corpus, on this 8 GB CPU-only machine?

The secondary measurement is whether that system stays inside a practical RAM and latency envelope on the same machine.

System B separates “having structured memory” from “exposing it through MCP”. A gain from A to B is a memory effect. A gain from B to C is a protocol-boundary effect. The write-up keeps those claims apart.

## Shared controls

All three systems use:

- the same chunker, the same SQLite corpus, and the same embedding model
- the same chat model, `temperature: 0`, and the same `num_ctx` and `num_predict`
- the same answer instructions and the same evidence post-check
- the same `k` (5 chunks, 5 memories where memory exists)
- one question at a time, in a fresh thread, unless the item is marked multi-turn

Ollama `seed` is set when the installed server accepts it, and the report states whether it did.

Items are scored from gold ids and required phrases. A person can audit every item because the corpus is original and small.

## Systems

### System A — stateless local RAG

```text
question → embed → top-k chunks → one chat call → answer
```

No project memory, no MCP, no routing. Multi-turn items may include the prior turns of that item as plain text in the prompt, and still have no stored memory. Cross-session items start blank, which is the baseline for “the process restarted and nothing was kept”.

### System B — persistent memory without MCP

The same LangGraph nodes as System C. Memory and document calls invoke `core` directly. No MCP client and no MCP server process are running during this condition.

### System C — persistent memory through MCP

The production graph. Retrieve and remember call the MCP tools over Streamable HTTP against a locally started server. The server uses the same `core` functions as System B.

If System C cannot open MCP, the item is scored as a task failure. It is not retried through System B’s path.

## What “comparable” means

| Factor | Held fixed | Allowed to vary |
| --- | --- | --- |
| Corpus and gold labels | yes | |
| Models and decoding limits | yes | |
| Top-k and prompt template for the answer | yes | |
| How memory is fetched | | A has none, B calls `core`, C calls MCP |
| Process count | | C runs the MCP process; A and B do not |

Routing accuracy is reported for B and C only. A is marked not applicable for tool-selection metrics.

## Dataset

Path: `evaluation/datasets/controlled/`.

The corpus is a fictional project named Harbor, written for this repository. It is not a dump of copyrighted papers. It is small enough to grade by hand: about 10 documents, under about 15 KB of text each, plus two imported conversations and a pre-seeded memory vault.

Planted content:

| Plant | Purpose |
| --- | --- |
| A decision record on retrieval storage, with a reason that cites hardware | Cross-session memory question in the brief |
| A later decision that supersedes an earlier library choice | Temporal update |
| Two facts that contradict each other on a minor setting | Conflict |
| A note that is on-topic but not the answer | Irrelevant rejection |
| A fact split across two documents | Cross-document |
| A fact that appears only in a conversation import | Import recall |
| A casual aside marked as not durable | Must not be stored by the policy unit test |
| A decoy project fact in a second project id | Project boundary |

Question file: `questions.yaml`. About 24 items, at least two of each class:

1. Direct retrieval from one document.
2. Cross-document reasoning.
3. Memory recall of a seeded record.
4. Temporal update, where the older decision is the wrong answer.
5. Conflict, where the graded behavior is to mention both sides.
6. Irrelevant-memory rejection, where using the decoy is wrong.
7. Multi-turn, with `prior_turns` inside the item.
8. Cross-session, scored against the seeded vault for B and C, and against an empty memory for A.

Gold record:

```yaml
id: q01
category: memory_recall
session: cross
question: What architecture did I decide for the retrieval system and why?
prior_turns: []
expects_route: memory
gold_memory_ids: [decision_retrieval_sqlite]
gold_chunk_ids: []
required_points:
  - exact cosine search in SQLite
  - 8 GB RAM constraint
forbidden_points:
  - Qdrant
acceptable_grounding: [known_from_memory]
```

`required_points` are short phrases a human grader can see in the answer. They are matched case-insensitively. This is a rubric, not a claim of full semantic equivalence.

A second scripted run, separate from the 24-item frozen vault, executes a write turn, restarts the processes, and asks a follow-up. That run checks the definition-of-done persistence path. Its model-written memory is inspected by hand and is not mixed into the Recall tables for the frozen vault, because the model’s write is itself a variable.

## Retrieval metrics

Computed on questions that have non-empty `gold_chunk_ids`. Retrieved list is the ranked chunk ids before the answer call.

- Recall@k = fraction of gold chunks present in the top k, macro-averaged over questions.
- Precision@k = fraction of the top k that are gold, macro-averaged.
- MRR = mean of `1 / rank` of the first gold chunk, or 0 if absent.
- nDCG@k with binary relevance (gold = 1).

k is 5, matching the agent bound. The report also prints k = 1 and k = 3 so a single cutoff is not the whole story.

## Memory metrics

Computed on questions with memory gold, plus the policy unit tests.

- Memory Recall: fraction of `gold_memory_ids` returned by memory search.
- Memory Precision: fraction of returned memories that are gold.
- Memory Update Accuracy: on the scripted revision items, 1 when the new record is active, the old id is `superseded`, and the old body is unchanged.
- Conflict Rate: fraction of conflict-category items where the answer mentions both gold sides and the store still contains both records.

Policy unit tests are deterministic and do not use Ollama. They cover reject, duplicate, decision non-overwrite, and the capacity cap.

## Agent metrics

- Task Completion Rate: fraction of items where every `required_points` entry is present and no `forbidden_points` entry is present.
- Tool Selection Accuracy: fraction of B and C items whose recorded route equals `expects_route`.
- Tool Call Success Rate: fraction of MCP or direct tool calls with `ok: true`.
- Grounded Answer Rate: fraction of items whose final grounding label is inside `acceptable_grounding` and whose citations are a subset of the retrieved ids.
- Error Rate: fraction of items whose answer contains a `forbidden_points` entry or a citation id that was not retrieved.

An item can fail grounding and still pass task completion. Both numbers are reported.

## System metrics

For each system, on the full question list, recorded once per item and summarized with median and max:

- RSS at turn start and end
- peak RSS during the turn
- wall-clock response latency
- retrieval latency inside the turn
- indexing time and peak RSS on a clean rebuild of the controlled corpus
- vault size in bytes after indexing

CPU time is recorded with `psutil.Process.cpu_times()` when the platform provides it, and omitted with a note when it does not.

## Ablation

The ablation asks which memory content helps, independent of MCP. It runs on the System B call path so a transport failure cannot be mistaken for a memory effect.

| Condition | What the retriever may read |
| --- | --- |
| A. No persistent memory | Chunks only. Same as System A. |
| B. Raw conversation memory | Top-k turns from imported and stored transcripts, embedded as their own rows. No structured records. |
| C. Structured memory | Facts, decisions, goals, knowledge, status. No episodes. No raw turns. |
| D. Structured plus episodic | Condition C plus episodes and conversation summaries. |
| E. Structured, episodic, and document RAG | Condition D plus the document index. This is System B’s full context. |

Each condition answers the same question file. The report table is Task Completion, Grounded Answer Rate, and median latency. A condition is described as better only when its task-completion count exceeds the previous relevant condition on this set. With 24 items, the report also lists the item ids that flipped, so a one-item swing is visible.

System C is not an ablation row. It is compared with System B full context (condition E) in the main three-system table.

## Vector-search gate

Phase 4 runs this before any non-default index is coded into the MCP path.

Candidates, same embeddings, same queries from the direct-retrieval slice:

| Candidate | Notes |
| --- | --- |
| SQLite float32 blobs, exact cosine in NumPy, batched reads | Default |
| `sqlite-vec` | Only if the installed wheel loads on this Windows machine |
| `hnswlib` saved to a file | Only if exact search misses the latency bar |

FAISS, LanceDB, Qdrant, PostgreSQL, and Redis are not in the gate.

Adopt a replacement only if, on this machine and this corpus:

- Recall@5 is at least the exact-search Recall@5 minus 0.02
- median search latency is under 200 ms
- extra peak RSS during search is under 150 MB
- the implementation stays in-process and disk-backed

If exact search already meets the latency bar, it remains the implementation. The gate results go in `evaluation/reports/vector_gate.md`.

## Resource report

`evaluation/reports/resources.md` will contain the system-metric table. Phase 0 does not invent measurements.

Indexing is also timed on a repeated run where every hash matches, to show that unchanged documents are not re-embedded.

## Threats to validity

- A 3B model may route poorly. That outcome is reported as Tool Selection Accuracy, not patched with an open tool loop.
- Twenty-four hand-built items can be overfit by prompt edits. Prompts are frozen before the reported run, and the item-level flip list is part of the result.
- System C uses an extra process, so it can lose on latency and RAM while winning on task completion. Both are published.
- Seeded memory in the frozen vault is cleaner than memory the model writes. The restart script is the check on the messy path, and it is labeled as such.
- Exact search quality on a tiny corpus will not by itself justify the index choice for a large corpus. The project claims the choice for this hardware and this workload.

## Implementation note for Phase 9

Runners live in `evaluation/experiments/` and call the baselines or the production graph. They write `evaluation/reports/comparison.md` with the metric tables and the per-item outcomes. They do not change tool code to improve a score.
