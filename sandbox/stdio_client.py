import shlex
from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager


@asynccontextmanager
async def stdio_tools(command: str):
    commands = shlex.split(command)
    if not commands:
        raise ValueError("Command cannot be empty")
    cmd = commands[0]
    args = commands[1:]
    server_params = StdioServerParameters(
        command=cmd,
        args=args,
    )
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session
