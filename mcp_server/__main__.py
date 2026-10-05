"""Run the Memoria MCP server over Streamable HTTP."""

from core.config import Settings
from core.ollama import OllamaEmbedder
from mcp_server.server import build_server


def main() -> None:
    settings = Settings()
    server = build_server(settings.data_root, OllamaEmbedder())
    server.run(transport="streamable-http", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
