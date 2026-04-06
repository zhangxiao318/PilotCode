"""MCP command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..services.mcp_client import get_mcp_client, MCPConfig


async def mcp_command(args: list[str], context: CommandContext) -> str:
    """Handle /mcp command."""
    client = get_mcp_client()

    if not args:
        # List connections
        if not client.connections:
            return "No MCP servers connected.\n\nUse '/mcp add <name> <command>' to add one."

        lines = ["MCP Servers:", ""]
        for name, conn in client.connections.items():
            tool_count = len(conn.tools) if conn.tools else 0
            lines.append(f"  • {name}")
            lines.append(f"    Command: {conn.config.command}")
            lines.append(f"    Tools: {tool_count}")

        return "\n".join(lines)

    action = args[0]

    if action == "add":
        if len(args) < 3:
            return "Usage: /mcp add <name> <command> [args...]"

        name = args[1]
        command = args[2]
        cmd_args = args[3:] if len(args) > 3 else []

        config = MCPConfig(command=command, args=cmd_args)

        try:
            await client.connect(name, config)
            return f"Added MCP server: {name}"
        except Exception as e:
            return f"Failed to add MCP server: {e}"

    elif action == "remove":
        if len(args) < 2:
            return "Usage: /mcp remove <name>"

        name = args[1]

        if name not in client.connections:
            return f"MCP server not found: {name}"

        await client.disconnect(name)
        return f"Removed MCP server: {name}"

    elif action == "tools":
        if len(args) < 2:
            return "Usage: /mcp tools <server_name>"

        name = args[1]

        if name not in client.connections:
            return f"MCP server not found: {name}"

        conn = client.connections[name]
        tools = conn.tools or []

        lines = [f"Tools from {name}:", ""]
        for tool in tools:
            lines.append(f"  • {tool.get('name', 'unnamed')}")

        return "\n".join(lines) if tools else f"No tools available from {name}"

    else:
        return f"Unknown action: {action}. Use: add, remove, tools"


register_command(CommandHandler(name="mcp", description="Manage MCP servers", handler=mcp_command))
