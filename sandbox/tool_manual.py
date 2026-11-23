from typing import Any, Sequence


def generate_tool_manual(tools: Sequence[Any]) -> str:
    """Generate human-readable documentation for available MCP tools.

    Args:
        tools: Collection of MCP Tool objects containing schemas and descriptions.

    Returns:
        str: Formatted documentation manual string describing the tools and parameters.
    """
    manual = ["AVAILABLE MCP TOOLS"]

    for tool in tools:
        manual.append(f"\n{tool.name}")
        manual.append(f"Description: {tool.description or 'No description available'}")

        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        manual.append("Parameters:")

        if not properties:
            manual.append("  None")
            continue

        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "unknown")

            is_required = param_name in required
            requirement = "required" if is_required else "optional"

            manual.append(
                f"  - {param_name} ({param_type}, {requirement})"
            )

    return "\n".join(manual)
