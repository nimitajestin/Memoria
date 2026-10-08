# T6 final polish sweep

Golden pytest (this machine): **77 passed, 1 skipped, 1 deselected** in 106.40s (`python -m pytest`).

## Repo root

Present: `app/`, `agent/`, `mcp_server/`, `ingestion/`, `storage/`, `evaluation/`, `tests/`, `scripts/`, `report/`, `docs/`, `docker-compose.yml`, `Dockerfile`, `README.md`, plus config (`pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`, `.dockerignore`, `.streamlit/`).

**Flag (do not move):** `core/` is the shared library (ADR-003). The polish checklist omitted it; it is not a stray.

**Flag:** `.streamlit/config.toml` hides the Streamlit Deploy toolbar (T4). `.pytest_cache/` is local and gitignored.

## Docker

`docker compose build` after the PYTHONPATH fix. Runtime smoke: `mcp` :8765 and `app` :8501.

## Demo

```powershell
.\scripts\start_demo.ps1
```

Open **http://localhost:8501**
