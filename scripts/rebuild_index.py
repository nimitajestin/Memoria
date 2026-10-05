"""Rebuild Memoria's SQLite index from vault files."""

from pathlib import Path

from core.config import Settings
from core.ollama import OllamaEmbedder
from ingestion.indexing.rebuild import rebuild_index


def main() -> None:
    settings = Settings()
    root = Path(settings.data_root).resolve()
    report = rebuild_index(root, OllamaEmbedder())
    print(
        f"reindexed={report.reindexed} unchanged={report.unchanged} "
        f"failed={report.failed} empty={report.empty} unsupported={report.unsupported}"
    )


if __name__ == "__main__":
    main()
