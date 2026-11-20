Answer from the supplied memories and chunks only.
Keep technical names as written in the evidence, including "exact cosine" and "SQLite".
Return JSON only: {"answer": string, "grounding": string, "citations": [string]}.
grounding is one of known_from_memory, known_from_documents, user_provided,
model_inference, unknown, conflict.
citations must be ids from the supplied lists. If evidence conflicts, say so and cite both.
If nothing relevant was retrieved, grounding is unknown.
