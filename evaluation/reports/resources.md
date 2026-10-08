# Resource measurements

Idle RSS is this Python process before Harbor work. Scale indexing uses HashEmbedder copies of Harbor text so 1000 live Ollama embeds are not required on 8 GB RAM. One live Harbor index + one `phi3:mini` turn is reported separately when Ollama responds.

- Idle RSS: 73.1 MB

## Live Harbor (nomic-embed-text + phi3:mini)

- Indexing: 22.22 s, RSS start/end/peak 74.7/29.2/74.7 MB
- Retrieval: 919.9 ms, hits=5, RSS peak 31.6 MB
- Stateless LLM turn: 41.16 s, RSS peak 32.6 MB, answer_chars=7

## Indexing scale (HashEmbedder)

| Documents | Index time (s) | Vault bytes | Peak RSS (MB) |
| --- | --- | --- | --- |
| 10 | 0.63 | 82183 | 19.4 |
| 100 | 39.73 | 231373 | 21.4 |
| 500 | 74.48 | 938117 | 20.1 |
| 1000 | 164.74 | 1809261 | 29.6 |

Idle RSS after measurements: 24.7 MB

