from typing import Any, Callable
from collections.abc import Sequence
from .tool_manual import generate_tool_manual
from multiprocessing.connection import Connection


def tool_wrapper(
    tool_name: str,
    input_schema: dict[str, Any],
    connection: Connection
) -> Callable[..., Any]:
    """Create a client-side wrapper callable for an MCP tool.

    Validates tool arguments against input_schema and sends tool call requests
    across the IPC connection to the host process.

    Args:
        tool_name: Name of the MCP tool to invoke.
        input_schema: JSON Schema dictionary defining tool parameters.
        connection: IPC connection to communicate with the host process.

    Returns:
        Callable[..., Any]: Function that validates inputs and invokes the tool.
    """
    properties = list(input_schema.get("properties", {}).keys())

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """Validate parameters and invoke the remote MCP tool via IPC.

        Args:
            *args: Positional arguments mapped to schema properties.
            **kwargs: Keyword arguments for schema properties.

        Returns:
            Any: Extracted result or response data from the MCP tool call.

        Raises:
            TypeError: If arguments are invalid, missing, or duplicated.
            RuntimeError: If the remote tool call returns an error or unexpected response.
        """
        if len(args) > len(properties):
            raise TypeError("Too many positional arguments")
        arguments = dict(zip(properties, args))
        for key, value in kwargs.items():
            if key in arguments:
                raise TypeError(f"Multiple values for argument '{key}'")
            arguments[key] = value
        unknown = set(arguments) - set(properties)
        if unknown:
            raise TypeError(f"Unknown arguments: {unknown}")
        required = input_schema.get("required", [])
        missing = set(required) - set(arguments)
        if missing:
            raise TypeError(f"Missing arguments: {missing}")
        connection.send({
            "type": "mcp_tool_call",
            "name": tool_name,
            "arguments": arguments
        })
        response = connection.recv()
        if response["type"] == "mcp_tool_error":
            raise RuntimeError(response["error"])
        if response["type"] != "mcp_tool_result":
            raise RuntimeError("Unexpected response from parent process")
        res_data = response["result"]
        if (
            isinstance(res_data, dict)
            and res_data.get("structured_content")
            and isinstance(res_data["structured_content"], dict)
            and "result" in res_data["structured_content"]
        ):
            return res_data["structured_content"]["result"]
        if isinstance(res_data, dict) and res_data.get("content"):
            texts = [
                c["text"]
                for c in res_data["content"]
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            if texts:
                return "\n".join(texts) if len(texts) > 1 else texts[0]
        return res_data

    wrapper.__name__ = tool_name
    return wrapper


def build_tool_namespace(
    tools: Sequence[Any] | None,
    connection: Connection
) -> dict[str, Any]:
    """Build the dictionary of tool callables and manual documentation for the sandbox.

    Args:
        tools: Collection of MCP Tool objects, or None.
        connection: IPC connection to communicate with the host process.

    Returns:
        dict[str, Any]: Mapping of tool names and manual helpers to their callables or values.
    """
    tool_list = list(tools) if tools else []
    manual = generate_tool_manual(tool_list)
    namespace: dict[str, Any] = {
        "tool_manual": manual,
        "sandbox_manual": manual,
        "tools_manual": manual,
        "get_manual": lambda: manual,
        "get_tool_manual": lambda: manual,
    }
    for tool in tool_list:
        namespace[tool.name] = tool_wrapper(
            tool.name,
            tool.input_schema,
            connection
        )
    return namespace
