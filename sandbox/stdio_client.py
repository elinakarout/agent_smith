import os
import shlex
from collections.abc import AsyncIterator
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters


@asynccontextmanager
async def stdio_tools(command: str) -> AsyncIterator[ClientSession]:
    """Launch an MCP server subprocess via stdio and yield an initialized session.

    Args:
        command: Command string to launch the MCP server subprocess.

    Yields:
        ClientSession: Initialized MCP client session connected to the subprocess.

    Raises:
        ValueError: If the command string is empty.
    """
    commands = shlex.split(command)
    if not commands:
        raise ValueError("Command cannot be empty")
    cmd = commands[0]
    args = commands[1:]
    server_params = StdioServerParameters(
        command=cmd,
        args=args,
        env=dict(os.environ),
    )
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session
