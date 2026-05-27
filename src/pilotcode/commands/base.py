"""Base command definitions and registry."""

import io
import os
import sys
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field

from ..types.command import CommandContext, CommandType


@dataclass
class CommandHandler:
    """Handler for a command."""

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    aliases: list[str] = field(default_factory=list)
    is_enabled: bool = True
    command_type: CommandType = "local"
    hidden: bool = False  # Hidden from default /help, shown with /help all


class CommandRegistry:
    """Registry for commands."""

    def __init__(self):
        self._commands: dict[str, CommandHandler] = {}
        self._aliases: dict[str, str] = {}
        self._user_aliases: dict[str, Any] = {}
        self._load_user_aliases()

    def _aliases_path(self):
        from ..utils.paths import get_config_dir

        return get_config_dir() / "aliases.json"

    def _load_user_aliases(self):
        path = self._aliases_path()
        if not path.exists():
            return
        try:
            import json

            self._user_aliases = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._user_aliases = {}

    def _save_user_aliases(self):
        path = self._aliases_path()
        try:
            import json

            path.write_text(
                json.dumps(self._user_aliases, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def register(self, handler: CommandHandler) -> None:
        """Register a command handler."""
        self._commands[handler.name] = handler

        # Register aliases
        for alias in handler.aliases:
            self._aliases[alias] = handler.name

    def resolve(self, name: str) -> tuple[str | None, list[str]]:
        """Resolve a command name, returning (command_name, default_args).

        Supports two alias formats:
        - Legacy string: {"br": "branch"}
        - With default args: {"br": {"command": "git", "args": ["branch"]}}
        """
        if name in self._commands:
            return name, []
        if name in self._user_aliases:
            data = self._user_aliases[name]
            if isinstance(data, str):
                return data, []
            return data.get("command"), data.get("args", [])
        if name in self._aliases:
            return self._aliases[name], []
        return None, []

    def get(self, name: str) -> CommandHandler | None:
        """Get command by name or alias."""
        resolved, _ = self.resolve(name)
        if resolved:
            return self._commands.get(resolved)
        return None

    def get_all(self) -> list[CommandHandler]:
        """Get all registered commands."""
        return list(self._commands.values())

    def has_command(self, name: str) -> bool:
        """Check if command exists."""
        return self.resolve(name)[0] is not None

    def set_user_alias(
        self, alias: str, command: str, default_args: list[str] | None = None
    ) -> None:
        """Set a user-defined alias.

        Args:
            alias: The alias name (e.g., "br")
            command: The target command name (e.g., "git")
            default_args: Optional default args to prepend (e.g., ["branch"])
        """
        if default_args:
            self._user_aliases[alias] = {"command": command, "args": list(default_args)}
        else:
            self._user_aliases[alias] = command
        self._save_user_aliases()

    def remove_user_alias(self, alias: str) -> bool:
        """Remove a user-defined alias."""
        if alias not in self._user_aliases:
            return False
        del self._user_aliases[alias]
        self._save_user_aliases()
        return True

    def clear_user_aliases(self) -> None:
        """Remove all user-defined aliases."""
        self._user_aliases.clear()
        self._save_user_aliases()

    def get_user_aliases(self) -> dict[str, Any]:
        """Get all user-defined aliases."""
        return dict(self._user_aliases)


# Global registry
_global_registry: CommandRegistry | None = None


def get_command_registry() -> CommandRegistry:
    """Get global command registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = CommandRegistry()
    return _global_registry


# ---------------------------------------------------------------------------
# Unified output capture for command handlers
#
# Problem: many handlers mix console.print()/print() (writes to stdout) with
# return strings. The TUI sees both, causing duplicate/empty lines.
# Solution: wrap every registered handler to capture stdout + module-level
# Console instances, then merge with the return value.
# ---------------------------------------------------------------------------


class _TtyStringIO(io.StringIO):
    """StringIO that pretends to be a TTY so Rich keeps colors/markup."""

    def isatty(self) -> bool:
        return True


def _patch_module_consoles(buf: io.StringIO):
    """Temporarily redirect module-level Console instances to *buf*.

    This catches console.print() calls from commands that created
    ``console = Console()`` at import time (before stdout was redirected).
    """
    try:
        import rich.console
    except Exception:
        return []

    patched: list[tuple[Any, Any]] = []
    for mod in list(sys.modules.values()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file is None:
            continue
        # Only touch our own command modules
        if "pilotcode/commands" not in str(mod_file):
            continue
        obj = getattr(mod, "console", None)
        if isinstance(obj, rich.console.Console):
            old_file = obj.file
            obj.file = buf
            patched.append((obj, old_file))
    return patched


def _unpatch_module_consoles(patched: list[tuple[Any, Any]]) -> None:
    for console, old_file in patched:
        console.file = old_file


def _merge_output(result: Any, captured: str) -> Any:
    """Merge a handler's return value with captured stdout output."""
    cap = captured.rstrip("\n")
    if isinstance(result, str):
        res = result.strip()
        if cap and res:
            return cap + "\n\n" + res
        return cap or res
    if cap:
        return cap
    return result


def _wrap_handler(original: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap a command handler to capture all stdout output."""

    async def _wrapped(*args, **kwargs):
        buf = _TtyStringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        patched = _patch_module_consoles(buf)
        try:
            result = await original(*args, **kwargs)
        finally:
            _unpatch_module_consoles(patched)
            sys.stdout = old_stdout
        return _merge_output(result, buf.getvalue())

    return _wrapped


def register_command(handler: CommandHandler) -> CommandHandler:
    """Register a command to global registry.

    The handler is automatically wrapped so that any stdout/console output
    is captured and merged with the return value, preventing duplicate or
    empty lines in the TUI.
    """
    handler.handler = _wrap_handler(handler.handler)
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
    Treats file paths (e.g. /home/user/...) as normal input, not commands.
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

    # If it looks like a file path (contains /), treat as normal input
    if "/" in command_name:
        return None, []

    # If it's not a registered command or alias, treat as normal input
    registry = get_command_registry()
    if registry.resolve(command_name)[0] is None:
        return None, []

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

    # Resolve alias (including default args)
    registry = get_command_registry()
    resolved_name, default_args = registry.resolve(command_name)

    if resolved_name is None:
        # Unknown command
        return True, f"Unknown command: /{command_name}"

    handler = registry._commands.get(resolved_name)
    if handler is None:
        return True, f"Unknown command: /{command_name}"

    # Prepend default args from alias (e.g., /br -> /git branch)
    merged_args = default_args + args

    # Execute command (stdout capture is handled by the wrapper in register_command)
    try:
        result = await handler.handler(merged_args, context)
        return True, result
    except Exception as e:
        return True, f"Error executing /{command_name}: {str(e)}"


# Built-in commands


async def help_command(args: list[str], context: CommandContext) -> str:
    """Show help. Default shows core commands only; '/help all' shows everything."""
    registry = get_command_registry()
    show_all = bool(args and args[0] == "all")
    commands = registry.get_all()

    if show_all:
        visible = commands
    else:
        visible = [c for c in commands if not c.hidden]

    lines = ["Available commands:" + (" (all)" if show_all else " (core)"), ""]
    for cmd in sorted(visible, key=lambda c: c.name):
        alias_str = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  /{cmd.name}{alias_str} - {cmd.description}")

    hidden_count = len(commands) - len(visible)
    if hidden_count > 0 and not show_all:
        lines.append("")
        lines.append(f"  ... and {hidden_count} more. Use '/help all' to see all commands.")

    return "\n".join(lines)


async def clear_command(args: list[str], context: CommandContext) -> str:
    """Clear screen and reset conversation context."""
    os.system("clear" if os.name != "nt" else "cls")

    cleared = 0
    if context.query_engine is not None:
        cleared = len(context.query_engine.messages)
        context.query_engine.clear_history()
        # Reset compaction stats so the new session starts fresh
        context.query_engine._compaction_count = 0
        context.query_engine._last_compaction_message_count = 0

    return f"Screen and context cleared ({cleared} messages removed)."


async def quit_command(args: list[str], context: CommandContext) -> str:
    """Exit the application."""
    raise SystemExit(0)


async def new_command(args: list[str], context: CommandContext) -> str:
    """Start a new conversation, clearing all history."""
    if context.query_engine is None:
        return "Query engine not available."

    msg_count = len(context.query_engine.messages)
    context.query_engine.clear_history()

    # Reset compaction stats so the new session starts fresh
    context.query_engine._compaction_count = 0
    context.query_engine._last_compaction_message_count = 0

    return f"🆕 New conversation started. {msg_count} previous message(s) cleared."


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
        name="clear",
        description="Clear the screen and reset conversation context",
        handler=clear_command,
        aliases=["cls"],
    )
)

register_command(
    CommandHandler(
        name="quit", description="Exit the application", handler=quit_command, aliases=["exit", "q"]
    )
)

register_command(
    CommandHandler(
        name="new",
        description="Start a new conversation (clear history)",
        handler=new_command,
        aliases=["reset", "clear-history"],
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
        name="mcp-add",
        description="Add an MCP server",
        handler=mcp_add_command,
        aliases=[],
        hidden=True,
    )
)

register_command(
    CommandHandler(
        name="mcp-remove",
        description="Remove an MCP server",
        handler=mcp_remove_command,
        aliases=[],
        hidden=True,
    )
)
