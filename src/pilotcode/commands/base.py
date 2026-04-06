"""Base command definitions and registry."""

from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
import re

from ..types.command import Command, CommandContext, CommandType, PromptCommand, LocalCommand
from ..types.message import ContentBlock, TextBlock


@dataclass
class CommandHandler:
    """Handler for a command."""

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    aliases: list[str] = field(default_factory=list)
    is_enabled: bool = True
    command_type: CommandType = "local"


class CommandRegistry:
    """Registry for commands."""

    def __init__(self):
        self._commands: dict[str, CommandHandler] = {}
        self._aliases: dict[str, str] = {}

    def register(self, handler: CommandHandler) -> None:
        """Register a command handler."""
        self._commands[handler.name] = handler

        # Register aliases
        for alias in handler.aliases:
            self._aliases[alias] = handler.name

    def get(self, name: str) -> CommandHandler | None:
        """Get command by name or alias."""
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        return None

    def get_all(self) -> list[CommandHandler]:
        """Get all registered commands."""
        return list(self._commands.values())

    def has_command(self, name: str) -> bool:
        """Check if command exists."""
        return name in self._commands or name in self._aliases


# Global registry
_global_registry: CommandRegistry | None = None


def get_command_registry() -> CommandRegistry:
    """Get global command registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CommandRegistry()
    return _global_registry


def register_command(handler: CommandHandler) -> CommandHandler:
    """Register a command to global registry."""
    registry = get_command_registry()
    registry.register(handler)
    return handler


def get_all_commands() -> list[CommandHandler]:
    """Get all commands."""
    return get_command_registry().get_all()


def get_command_by_name(name: str) -> CommandHandler | None:
    """Get command by name."""
    return get_command_registry().get(name)


def parse_command(input_text: str) -> tuple[str | None, list[str]]:
    """Parse command from input text.

    Returns (command_name, args) or (None, []) if not a command.
    """
    input_text = input_text.strip()

    # Check if it starts with /
    if not input_text.startswith("/"):
        return None, []

    # Remove leading /
    input_text = input_text[1:]

    # Split into parts
    parts = input_text.split()
    if not parts:
        return None, []

    command_name = parts[0]
    args = parts[1:]

    return command_name, args


async def process_user_input(input_text: str, context: CommandContext) -> tuple[bool, Any]:
    """Process user input, checking for commands.

    Returns (is_command, result):
    - If is_command is True, result is the command output
    - If is_command is False, result is the original input (to send to model)
    """
    command_name, args = parse_command(input_text)

    if command_name is None:
        # Not a command, return as-is
        return False, input_text

    # Find command
    registry = get_command_registry()
    handler = registry.get(command_name)

    if handler is None:
        # Unknown command
        return True, f"Unknown command: /{command_name}"

    # Execute command
    try:
        result = await handler.handler(args, context)
        return True, result
    except Exception as e:
        return True, f"Error executing /{command_name}: {str(e)}"


# Built-in commands


async def help_command(args: list[str], context: CommandContext) -> str:
    """Show help."""
    registry = get_command_registry()
    commands = registry.get_all()

    lines = ["Available commands:", ""]
    for cmd in sorted(commands, key=lambda c: c.name):
        alias_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  /{cmd.name}{alias_str} - {cmd.description}")

    return "\n".join(lines)


async def clear_command(args: list[str], context: CommandContext) -> str:
    """Clear screen."""
    import os

    os.system("clear" if os.name != "nt" else "cls")
    return "Screen cleared."


async def quit_command(args: list[str], context: CommandContext) -> str:
    """Exit the application."""
    raise SystemExit(0)


async def mcp_add_command(args: list[str], context: CommandContext) -> str:
    """Add an MCP server."""
    if not args:
        return "[red]Usage: /mcp-add <name> <command_or_url>[/red]"
    name = args[0]
    # Placeholder: store MCP server config
    return f"[green]MCP server '{name}' added (placeholder)[/green]"


async def mcp_remove_command(args: list[str], context: CommandContext) -> str:
    """Remove an MCP server."""
    if not args:
        return "[red]Usage: /mcp-remove <name>[/red]"
    name = args[0]
    return f"[green]MCP server '{name}' removed (placeholder)[/green]"


async def resume_command(args: list[str], context: CommandContext) -> str:
    """Resume a saved session."""
    import os

    session_path = os.path.join(context.cwd, ".pilotcode_session.json")
    if args:
        session_path = args[0] if os.path.isabs(args[0]) else os.path.join(context.cwd, args[0])

    if not os.path.exists(session_path):
        return f"[red]No saved session found at {session_path}[/red]"

    if context.query_engine is None:
        return "[red]Query engine not available[/red]"

    success = context.query_engine.load_session(session_path)
    if success:
        msg_count = len(context.query_engine.messages)
        return f"[green]Session resumed from {session_path} ({msg_count} messages loaded)[/green]"
    return f"[red]Failed to load session from {session_path}[/red]"


# Register built-in commands
register_command(
    CommandHandler(
        name="help", description="Show available commands", handler=help_command, aliases=["h", "?"]
    )
)

register_command(
    CommandHandler(
        name="clear", description="Clear the screen", handler=clear_command, aliases=["cls"]
    )
)

register_command(
    CommandHandler(
        name="quit", description="Exit the application", handler=quit_command, aliases=["exit", "q"]
    )
)

register_command(
    CommandHandler(
        name="resume",
        description="Resume a saved conversation session",
        handler=resume_command,
        aliases=[],
    )
)

register_command(
    CommandHandler(
        name="mcp-add", description="Add an MCP server", handler=mcp_add_command, aliases=[]
    )
)

register_command(
    CommandHandler(
        name="mcp-remove",
        description="Remove an MCP server",
        handler=mcp_remove_command,
        aliases=[],
    )
)
