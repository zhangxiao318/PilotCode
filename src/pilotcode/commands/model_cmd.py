"""Model command implementation — read-only model info display."""

from .base import CommandHandler, register_command, CommandContext
from ..utils.config import get_global_config


async def model_command(args: list[str], context: CommandContext) -> str:
    """Handle /model command — display current model capabilities and available models."""
    from ..utils.models_config import (
        get_model_info,
        get_all_models,
    )

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
    lines.extend(["", "To switch model, use: python3 -m pilotcode configure"])

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="model", description="Show current model and available models", handler=model_command
    )
)
