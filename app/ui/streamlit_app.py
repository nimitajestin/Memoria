"""Memoria Streamlit app. Chat goes through the agent; Memory and Documents read the vault."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.ui.chat import render_chat
from app.ui.documents_view import render_documents
from app.ui.memory_view import render_memory
from app.ui.services import list_projects
from app.ui.trace_view import render_trace
from core.config import Settings


def main() -> None:
    settings = Settings()
    root = Path(settings.data_root).resolve()
    st.set_page_config(page_title="Memoria", layout="wide")
    st.title("Memoria")
    projects = list_projects(root)
    ids = [item["id"] for item in projects] or ["project_harbor"]
    if "project_harbor" in ids:
        ids = ["project_harbor", *[pid for pid in ids if pid != "project_harbor"]]
    project_id = st.sidebar.selectbox("Project", ids)
    page = st.sidebar.radio("Page", ["Chat", "Memory", "Documents", "Trace"])
    if "history" not in st.session_state:
        st.session_state.history = []
        st.session_state.trace = []
    if page == "Chat":
        render_chat(st, root, project_id)
    elif page == "Memory":
        render_memory(st, root, project_id)
    elif page == "Documents":
        render_documents(st, root, project_id)
    else:
        render_trace(st)


if __name__ == "__main__":
    main()
