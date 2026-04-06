"""Env command implementation."""

import os
from .base import CommandHandler, register_command, CommandContext


async def env_command(args: list[str], context: CommandContext) -> str:
    """Handle /env command."""
    if not args:
        # Show key environment variables
        keys = [
            "HOME",
            "USER",
            "SHELL",
            "PATH",
            "PWD",
            "EDITOR",
            "TERM",
            "LANG",
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "CLAUDECODE_THEME",
            "CLAUDECODE_MODEL",
        ]

        lines = ["Environment Variables:", ""]
        for key in keys:
            value = os.environ.get(key, "<not set>")
            if "KEY" in key or "TOKEN" in key or "SECRET" in key:
                value = "*" * min(len(value), 10) if value != "<not set>" else value
            lines.append(f"  {key}={value}")

        return "\n".join(lines)

    action = args[0]

    if action == "get":
        if len(args) < 2:
            return "Usage: /env get <variable>"

        var = args[1]
        value = os.environ.get(var, "<not set>")
        return f"{var}={value}"

    elif action == "set":
        if len(args) < 3:
            return "Usage: /env set <variable> <value>"

        var = args[1]
        value = " ".join(args[2:])

        os.environ[var] = value
        return f"Set {var}={value}"

    elif action == "list":
        # List all env vars (truncated)
        lines = ["All Environment Variables:", ""]
        for key in sorted(os.environ.keys())[:50]:
            value = os.environ[key]
            if len(value) > 50:
                value = value[:50] + "..."
            lines.append(f"  {key}={value}")

        if len(os.environ) > 50:
            lines.append(f"\n... and {len(os.environ) - 50} more")

        return "\n".join(lines)

    else:
        return f"Unknown action: {action}. Use: get, set, list"


register_command(
    CommandHandler(name="env", description="Environment variables", handler=env_command)
)
