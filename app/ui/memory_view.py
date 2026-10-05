from pathlib import Path

from app.ui.services import list_memory


def render_memory(st, root: Path, project_id: str) -> None:
    rows = list_memory(root, project_id)
    st.write(f"{len(rows)} active records")
    for row in rows:
        st.markdown(f"**{row.get('type')}** `{row.get('id')}`")
        st.write(row.get("statement") or row.get("decision") or row.get("summary") or row.get("title") or "")
