# Incremental indexing

Harbor must not re-embed unchanged files.

MARKER_INCREMENTAL_HASH: If a Harbor document byte hash is unchanged, the indexer skips embedding.

Changed files are re-indexed one document at a time. Deleted files drop their chunks.
