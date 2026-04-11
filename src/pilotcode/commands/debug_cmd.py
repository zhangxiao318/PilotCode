"""Debug command implementation."""

import sys
from .base import CommandHandler, register_command, CommandContext


async def debug_command(args: list[str], context: CommandContext) -> str:
    """Handle /debug command."""
    if not args:
        return """Debug options:
  /debug state    - Show internal state
  /debug config   - Show configuration
  /debug tools    - List tool registry
  /debug commands - List command registry
"""

    action = args[0]

    if action == "state":
        lines = [
            "Internal State:",
            "=" * 40,
            f"Working directory: {context.cwd}",
            f"Python version: {sys.version}",
            f"Platform: {sys.platform}",
        ]

        # Add tool count
        from ..tools.registry import get_all_tools

        tools = get_all_tools()
        lines.append(f"Registered tools: {len(tools)}")

        # Add command count
        from ..commands.base import get_all_commands

        commands = get_all_commands()
        lines.append(f"Registered commands: {len(commands)}")

        return "\n".join(lines)

    elif action == "config":
        from ..utils.config import get_global_config

        config = get_global_config()

        lines = [
            "Configuration:",
            "=" * 40,
        ]

        for key, value in config.__dict__.items():
            if not key.startswith("_"):
                # Hide sensitive values
                if "key" in key.lower() or "token" in key.lower():
                    value = "*" * min(len(str(value)), 10) if value else "<not set>"
                lines.append(f"{key}: {value}")

        return "\n".join(lines)

    elif action == "tools":
        from ..tools.registry import get_all_tools

        tools = get_all_tools()

        lines = [f"Registered Tools ({len(tools)}):", ""]
        for tool in sorted(tools, key=lambda t: t.name):
            aliases = f" ({', '.join(tool.aliases)})" if tool.aliases else ""
            lines.append(f"  {tool.name}{aliases}")

        return "\n".join(lines)

    elif action == "commands":
        from ..commands.base import get_all_commands

        commands = get_all_commands()

        lines = [f"Registered Commands ({len(commands)}):", ""]
        for cmd in sorted(commands, key=lambda c: c.name):
            aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  /{cmd.name}{aliases}")

        return "\n".join(lines)

    else:
        return f"Unknown action: {action}"


register_command(CommandHandler(name="debug", description="Debug tools", handler=debug_command))
