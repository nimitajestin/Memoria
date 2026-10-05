def render_trace(st) -> None:
    result = st.session_state.get("last_result")
    if result is None:
        st.info("Send a chat message to populate the trace.")
        return
    st.json(result.trace)
