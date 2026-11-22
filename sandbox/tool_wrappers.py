from multiprocessing.connection import Connection


def tool_wrapper(tool_name: str, input_schema: dict, connection: Connection):
    properties = list(input_schema.get("properties", {}).keys())

    def wrapper(*args, **kwargs):
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
        return response["result"]["structured_content"]["result"]

    wrapper.__name__ = tool_name
    return wrapper


def build_tool_namespace(tools: list, connection: Connection):
    namespace = {}
    for tool in tools:
        namespace[tool.name] = tool_wrapper(
            tool.name,
            tool.input_schema,
            connection
        )
    return namespace
