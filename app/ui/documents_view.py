from pathlib import Path

from app.ui.ingest import ingest_bytes, ingest_inbox, list_inbox, reindex_project
from app.ui.services import list_documents
from core.errors import StorageError


def render_documents(st, root: Path, project_id: str) -> None:
    uploads = st.file_uploader("Add files", accept_multiple_files=True)
    if uploads and st.button("Add files to vault"):
        added = 0
        errors: list[str] = []
        for item in uploads:
            try:
                ingest_bytes(root, project_id, item.name, item.getvalue())
                added += 1
            except StorageError as exc:
                errors.append(f"{item.name}: {exc}")
        if added:
            st.success(f"{added} files added, index pending")
        for message in errors:
            st.error(message)
    pending = list_inbox()
    if pending and st.button(f"Import from inbox ({len(pending)} files)"):
        added, errors = ingest_inbox(root, project_id)
        if added:
            st.success(f"{len(added)} files added, index pending")
            report = reindex_project(root, project_id)
            st.info(
                f"reindexed={report.reindexed} unchanged={report.unchanged} "
                f"failed={report.failed} unsupported={report.unsupported}"
            )
        for message in errors:
            st.error(message)
    if st.button("Reindex project"):
        report = reindex_project(root, project_id)
        st.info(
            f"reindexed={report.reindexed} unchanged={report.unchanged} "
            f"failed={report.failed} unsupported={report.unsupported}"
        )
    rows = list_documents(root, project_id)
    st.write(f"{len(rows)} documents")
    for row in rows:
        st.markdown(
            f"`{row.get('id')}` {row.get('filename')} — {row.get('status')} ({row.get('chunk_count')} chunks)"
        )
