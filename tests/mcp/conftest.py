import json
from pathlib import Path

import anyio
from mcp import Client

from core.retrieval.hash_embedder import HashEmbedder
from evaluation.datasets.controlled.load import HARBOR, load_harbor
from ingestion.indexing.pipeline import index_project
from mcp_server.server import build_server


def load_indexed_harbor(tmp_path: Path):
    load_harbor(tmp_path)
    embedder = HashEmbedder()
    index_project(tmp_path, HARBOR, embedder=embedder)
    server = build_server(tmp_path, embedder)
    return server, embedder


def call_tool(server, name: str, arguments: dict) -> dict:
    async def go() -> dict:
        async with Client(server) as client:
            result = await client.call_tool(name, arguments)
            return json.loads(result.content[0].text)

    return anyio.run(go)


def read_resource(server, uri: str) -> str:
    async def go() -> str:
        async with Client(server) as client:
            result = await client.read_resource(uri)
            contents = result.contents
            first = contents[0]
            return getattr(first, "text", str(first))

    return anyio.run(go)
