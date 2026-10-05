"""Process configuration. Models and paths come from the environment."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_root: Path = Path("./storage")
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text"
    mcp_url: str = "http://127.0.0.1:8765/mcp"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765
    log_level: str = "INFO"
