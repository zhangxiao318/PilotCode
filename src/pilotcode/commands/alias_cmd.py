"""User-defined command aliases."""

from .base import CommandHandler, register_command, CommandContext, get_command_registry


async def alias_command(args: list[str], context: CommandContext) -> str:
    """Manage user-defined command aliases.

    Usage:
      /alias                        - List all custom aliases
      /alias <name> <cmd> [args...] - Create alias
                                      e.g. /alias br git branch
      /alias rm <name>              - Remove an alias
      /alias clear                  - Clear all custom aliases
    """
    registry = get_command_registry()

    if not args:
        aliases = registry.get_user_aliases()
        if not aliases:
            return (
                "No custom aliases set.\n"
                "Use '/alias <name> <command> [args...]' to create one.\n"
                "Example: /alias br git branch"
            )
        lines = ["Custom aliases:"]
        for alias, data in sorted(aliases.items()):
            if isinstance(data, str):
                lines.append(f"  /{alias} -> /{data}")
            else:
                cmd = data.get("command", "?")
                extra = " ".join(data.get("args", []))
                lines.append(f"  /{alias} -> /{cmd} {extra}")
        return "\n".join(lines)

    action = args[0]

    if action == "rm":
        if len(args) < 2:
            return "Usage: /alias rm <name>"
        name = args[1]
        if registry.remove_user_alias(name):
            return f"Removed alias: /{name}"
        return f"Alias not found: /{name}"

    if action == "clear":
        registry.clear_user_aliases()
        return "All custom aliases cleared."

    # /alias <name> <command> [args...]
    if len(args) < 2:
        return (
            "Usage: /alias <name> <command> [args...]\n"
            "Examples:\n"
            "  /alias br git branch\n"
            "  /alias st git status\n"
            "  /alias ci git commit"
        )

    name = args[0]
    command = args[1]
    default_args = args[2:] if len(args) > 2 else []

    # Validate target command exists
    if not registry.has_command(command):
        return f"Unknown command: /{command}"

    # Prevent aliasing built-in aliases (to avoid confusion)
    if name in registry._aliases:
        return f"'{name}' is a built-in alias and cannot be overridden."

    registry.set_user_alias(name, command, default_args or None)
    if default_args:
        return f"Alias set: /{name} -> /{command} {' '.join(default_args)}"
    return f"Alias set: /{name} -> /{command}"


register_command(
    CommandHandler(
        name="alias",
        description="Manage custom command aliases",
        handler=alias_command,
        aliases=[],
    )
)
