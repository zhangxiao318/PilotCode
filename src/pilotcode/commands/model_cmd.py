"""Model command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..utils.config import get_config_manager, get_global_config


async def model_command(args: list[str], context: CommandContext) -> str:
    """Handle /model command."""
    from ..utils.models_config import (
        get_model_info,
        get_all_models,
        get_model_context_window,
        get_model_max_tokens,
    )

    if not args:
        # Show current model with detailed capability info
        config = get_global_config()
        current = config.default_model

        lines = [f"Current model: {current}", ""]

        model_info = get_model_info(current)
        if model_info:
            ctx = model_info.context_window
            ctx_str = f"{ctx // 1000}K" if ctx >= 1000 else str(ctx)
            max_tok = model_info.max_tokens
            max_tok_str = f"{max_tok // 1000}K" if max_tok >= 1000 else str(max_tok)

            lines.append("Capability:")
            lines.append(f"  Display name:   {model_info.display_name}")
            lines.append(f"  API model:      {model_info.default_model}")
            lines.append(f"  Provider:       {model_info.provider.value}")
            lines.append(f"  Context window: {ctx_str}")
            lines.append(f"  Max output:     {max_tok_str}")
            lines.append(f"  Tools:          {'Yes' if model_info.supports_tools else 'No'}")
            lines.append(f"  Vision:         {'Yes' if model_info.supports_vision else 'No'}")
            lines.append("")

        lines.append("Available models:")
        for name, info in get_all_models().items():
            marker = " *" if name == current else ""
            ctx = info.context_window
            ctx_str = f"{ctx // 1000}K" if ctx >= 1000 else str(ctx)
            lines.append(f"  {name:<15} {info.display_name:<25} ctx={ctx_str}{marker}")

        lines.extend(["", f"Base URL: {config.base_url}"])

        return "\n".join(lines)

    action = args[0]

    if action == "set":
        if len(args) < 2:
            return "Usage: /model set <model_name>"

        model_name = args[1]
        available = list(get_all_models().keys())
        if model_name not in available:
            return f"Unknown model: {model_name}. Available: {', '.join(available)}"

        config = get_global_config()
        config.default_model = model_name
        get_config_manager().save_global_config(config)

        # Show updated capability
        info = get_model_info(model_name)
        ctx_str = f"{info.context_window // 1000}K" if info and info.context_window >= 1000 else "?"
        return f"Model set to: {model_name} (context: {ctx_str})"

    elif action == "url":
        if len(args) < 2:
            config = get_global_config()
            return f"Current base URL: {config.base_url}"

        url = args[1]
        config = get_global_config()
        config.base_url = url
        get_config_manager().save_global_config(config)

        return f"Base URL set to: {url}"

    else:
        return f"Unknown action: {action}. Use: set, url"


register_command(
    CommandHandler(name="model", description="Manage model settings", handler=model_command)
)
