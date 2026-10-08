# F4 ingest sweep

Pytest: **84 passed, 2 skipped, 1 deselected**.

| Item | Status |
| --- | --- |
| F1 multi-file upload | DONE |
| F2 vault inbox import | DONE (code + commented compose volume) |
| F3 docs and tests | DONE |
| F4 sweep | DONE with F2 Chrome volume **BLOCKED** |

## Documents view (Chrome)

Code path: `st.file_uploader(..., accept_multiple_files=True)`, **Add files to vault**, **Reindex project**, and **Import from inbox (N files)** when `/vault/inbox` exists.

The inbox Docker volume is **commented out** in `docker-compose.yml` by design. Manual verification of the mounted folder:

1. `mkdir C:\MemoriaInbox`
2. Uncomment `- C:/MemoriaInbox:/vault/inbox:ro` under the `app` service.
3. `docker compose up -d --build` (needs Hub DNS).
4. Drop a `.md` file into `C:\MemoriaInbox`.
5. Open http://localhost:8501 → Documents → **Import from inbox**.
6. Confirm the file appears under `storage/documents/<project>/` and status becomes indexed after reindex.

Until that volume is uncommented, inbox import cannot be exercised in Compose.

## Screenshots

Documents view gained upload/reindex controls. Refresh `report/screenshots/documents.png` after a Chrome pass if the running image includes this branch.
