from core.config import Settings


def test_settings_read_model_names_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:1.5b")
    monkeypatch.setenv("EMBEDDING_MODEL", "all-minilm")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "qwen2.5:1.5b"
    assert settings.embedding_model == "all-minilm"
    assert settings.mcp_port == 8765


def test_storage_import_does_not_pull_in_mcp_or_streamlit() -> None:
    import subprocess
    import sys

    script = (
        "import sys; import core.storage; "
        "assert not any(n == 'mcp' or n.startswith('mcp.') for n in sys.modules); "
        "assert not any(n == 'streamlit' or n.startswith('streamlit.') for n in sys.modules); "
        "assert core.storage.MemoryRepository is not None"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
