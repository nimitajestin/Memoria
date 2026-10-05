from pathlib import Path

from app.ui.services import chat_turn


def render_chat(st, root: Path, project_id: str) -> None:
    system = st.selectbox("System", ["B", "C"], help="B uses core directly. C uses MCP_URL.")
    live = st.checkbox("Use Ollama chat", value=False)
    message = st.text_area("Message")
    if st.button("Send") and message.strip():
        result = chat_turn(
            root,
            project_id,
            message.strip(),
            system=system,
            live_ollama=live,
            prior_turns=st.session_state.history[-20:],
        )
        st.session_state.history.append({"role": "user", "content": message.strip()})
        st.session_state.history.append({"role": "assistant", "content": result.answer})
        st.session_state.trace = result.trace
        st.session_state.last_result = result
        st.markdown(result.answer)
        st.caption(f"grounding={result.grounding} route={result.route}")
    elif st.session_state.history:
        st.markdown(st.session_state.history[-1]["content"])
