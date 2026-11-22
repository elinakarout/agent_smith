import httpx
from mcp import ClientSession
from contextlib import asynccontextmanager
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def http_tools(url: str):
    async with httpx.AsyncClient() as http_client:
        async with streamable_http_client(
            url,
            http_client=http_client
        ) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session
