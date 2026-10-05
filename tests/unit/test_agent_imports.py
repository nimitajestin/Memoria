def test_agent_package_does_not_import_storage_writers() -> None:
    import subprocess
    import sys

    script = (
        "import agent.graph.build, agent.mcp_client, sys; "
        "mods = sys.modules; "
        "assert not any(n.startswith('core.storage') for n in mods); "
        "assert not any(n.startswith('mcp_server') for n in mods); "
        "assert 'core.memory.policy' not in mods"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
