import sys
import ast
import asyncio
import argparse
from typing import Any
from .config import read_config
from .http_client import http_tools
from .executor import SandboxExecutor
from .stdio_client import stdio_tools


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the sandbox CLI.

    Returns:
        argparse.Namespace: Parsed CLI options and arguments.
    """
    parser = argparse.ArgumentParser(description="Sandbox CLI")
    parser.add_argument("config_path", nargs="?", default=None,
                        help="Path to the sandbox configuration file")
    parser.add_argument("--mcp-stdio", type=str,
                        help="Command to launch an MCP server using stdio")
    parser.add_argument("--mcp-server", type=str,
                        help="URL of an MCP server using HTTP transport")
    parser.add_argument("--code", type=str,
                        help="Python code to execute")
    return parser.parse_args()


def split_into_statements(code: str) -> list[str]:
    """Split a multiline Python code string into individual top-level statements.

    Args:
        code: Python source code string.

    Returns:
        list[str]: List of source code segments for each top-level statement.
    """
    try:
        tree = ast.parse(code)
        statements = []
        for node in tree.body:
            seg = ast.get_source_segment(code, node)
            if seg:
                statements.append(seg)
        return statements if statements else [code]
    except Exception:
        return [code]


async def run_code_statements(
    executor: SandboxExecutor,
    code: str,
    session: Any | None = None
) -> None:
    """Execute Python code statement-by-statement in the sandbox REPL.

    Args:
        executor: Sandbox executor instance.
        code: Python source code string to run.
        session: Optional MCP client session for handling tool calls.
    """
    for stmt in split_into_statements(code):
        result = await executor.execute_repl(stmt, session)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.error_message:
            print(f"[Error] {result.error_message}")


async def repl_loop(
    executor: SandboxExecutor,
    session: Any | None = None
) -> None:
    """Run an interactive Read-Eval-Print Loop (REPL) using the sandbox executor.

    Args:
        executor: Sandbox executor instance.
        session: Optional MCP client session for handling tool calls.
    """
    while True:
        try:
            lines = []
            line = input(">>> ")
            while line.endswith("\\"):
                lines.append(line.rstrip("\\"))
                line = input("... ")
            lines.append(line)
            code = "\n".join(lines)
            if line == "exit()":
                print("Goodbye!")
                break
        except EOFError:
            print("\nGoodbye!")
            break

        result = await executor.execute_repl(code, session)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.error_message:
            print(f"[Error] {result.error_message}")


async def main() -> None:
    """Entrypoint for the sandbox CLI, setting up MCP tools and running code or REPL."""
    args = parse_arguments()
    config = read_config(args.config_path)
    executor = SandboxExecutor(config)

    if args.code is not None:
        code_to_run = args.code
    elif not sys.stdin.isatty():
        code_to_run = sys.stdin.read()
    else:
        code_to_run = None

    if args.mcp_stdio:
        async with stdio_tools(args.mcp_stdio) as session:
            tools = (await session.list_tools()).tools
            executor.start_repl(tools)
            try:
                if code_to_run is not None:
                    await run_code_statements(executor, code_to_run, session)
                else:
                    await repl_loop(executor, session)
            finally:
                executor.stop_repl()

    elif args.mcp_server:
        async with http_tools(args.mcp_server) as session:
            tools = (await session.list_tools()).tools
            executor.start_repl(tools)
            try:
                if code_to_run is not None:
                    await run_code_statements(executor, code_to_run, session)
                else:
                    await repl_loop(executor, session)
            finally:
                executor.stop_repl()

    else:
        executor.start_repl([])
        try:
            if code_to_run is not None:
                await run_code_statements(executor, code_to_run)
            else:
                await repl_loop(executor)
        finally:
            executor.stop_repl()


def run() -> None:
    """Run the sandbox CLI application using asyncio."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
