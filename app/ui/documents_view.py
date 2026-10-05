from pathlib import Path

from app.ui.services import list_documents


def render_documents(st, root: Path, project_id: str) -> None:
    rows = list_documents(root, project_id)
    st.write(f"{len(rows)} documents")
    for row in rows:
        st.markdown(
            f"`{row.get('id')}` {row.get('filename')} — {row.get('status')} ({row.get('chunk_count')} chunks)"
        )
