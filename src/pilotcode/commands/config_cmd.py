"""Config command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def config_command(args: list[str], context: CommandContext) -> str:
    """Handle /config command."""
    from ..utils.config import get_config_manager, get_global_config, GlobalConfig

    if not args:
        # Show all config
        config = get_global_config()
        lines = ["Configuration:", ""]
        for key, value in config.__dict__.items():
            if not key.startswith("_"):
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)

    action = args[0]

    if action == "get":
        if len(args) < 2:
            return "Usage: /config get <key>"

        key = args[1]
        config = get_global_config()
        value = getattr(config, key, None)

        if value is None:
            return f"Unknown key: {key}"

        return f"{key} = {value}"

    elif action == "set":
        if len(args) < 3:
            return "Usage: /config set <key> <value>"

        key = args[1]
        value = " ".join(args[2:])

        config = get_global_config()

        if not hasattr(config, key):
            return f"Unknown key: {key}"

        # Parse value
        current = getattr(config, key)
        if isinstance(current, bool):
            new_value = value.lower() in ("true", "1", "yes", "on")
        elif isinstance(current, int):
            new_value = int(value)
        else:
            new_value = value

        setattr(config, key, new_value)
        get_config_manager().save_global_config(config)

        return f"Set {key} = {new_value}"

    elif action == "reset":
        default = GlobalConfig()
        get_config_manager().save_global_config(default)
        return "Configuration reset to defaults"

    else:
        return f"Unknown action: {action}. Use: get, set, reset"


register_command(
    CommandHandler(
        name="config",
        description="Manage configuration",
        handler=config_command,
        aliases=["cfg", "settings"],
    )
)
