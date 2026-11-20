from pathlib import Path

from agent.llm import OllamaChat
from app.ui.services import chat_turn
from core.errors import StorageError


def render_chat(st, root: Path, project_id: str) -> None:
    if "chat_error" not in st.session_state:
        st.session_state.chat_error = ""
    if "suppress_submit" not in st.session_state:
        st.session_state.suppress_submit = False
    if "last_answer" not in st.session_state:
        st.session_state.last_answer = ""
    if "last_meta" not in st.session_state:
        st.session_state.last_meta = ""

    with st.form("memoria_chat", clear_on_submit=False):
        system = st.selectbox("System", ["B", "C"], help="B uses core directly. C uses MCP_URL.")
        live = st.checkbox("Use Ollama chat", value=False)
        message = st.text_area("Message")
        submitted = st.form_submit_button("Send")

    # A click that arrives while this script is inside chat_turn is queued and
    # delivered as the next run. Eat that one click so it cannot start a second turn.
    if st.session_state.suppress_submit:
        st.session_state.suppress_submit = False
        if submitted:
            submitted = False
            st.caption("A second Send arrived while the last turn was still running, so it was not sent again.")

    text = message.strip()
    if not submitted or not text:
        _show_saved(st)
        return

    st.session_state.chat_error = ""
    try:
        if live:
            chat = OllamaChat()
            with st.spinner(f"Checking whether {chat.model} is loaded…"):
                state = chat.ensure_resident()
            if state == "loaded":
                st.caption(f"Loaded {chat.model}. The next step is the reply, not another load.")
            else:
                st.caption(f"{chat.model} is already loaded. The next step is the reply.")
        with st.spinner("Running this turn. Leave this page open and do not send again."):
            result = chat_turn(
                root,
                project_id,
                text,
                system=system,
                live_ollama=live,
                prior_turns=st.session_state.history[-20:],
            )
    except StorageError as exc:
        st.session_state.chat_error = str(exc)
        st.session_state.suppress_submit = True
        _show_saved(st)
        return
    except Exception as exc:
        st.session_state.chat_error = f"This turn failed before an answer was saved: {exc}"
        st.session_state.suppress_submit = True
        _show_saved(st)
        return

    st.session_state.suppress_submit = True
    st.session_state.last_result = result
    st.session_state.trace = result.trace
    if result.error:
        st.session_state.chat_error = result.answer or result.error
        _show_saved(st)
        return
    st.session_state.history.append({"role": "user", "content": text})
    st.session_state.history.append({"role": "assistant", "content": result.answer})
    st.session_state.last_answer = result.answer
    st.session_state.last_meta = f"grounding={result.grounding} route={result.route}"
    st.markdown(result.answer)
    st.caption(st.session_state.last_meta)


def _show_saved(st) -> None:
    if st.session_state.chat_error:
        st.error(st.session_state.chat_error)
    if st.session_state.last_answer:
        st.markdown(st.session_state.last_answer)
        if st.session_state.last_meta:
            st.caption(st.session_state.last_meta)
