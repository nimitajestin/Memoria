# Retrieval storage

Harbor stores document vectors next to metadata.

MARKER_RETRIEVAL_SQLITE: Harbor retrieval uses exact cosine search over float32 vectors stored in SQLite.

The evaluation corpus is small, so exact search is the quality ceiling. A permanently running vector database is out of scope unless a later measurement on this machine proves it is necessary.
