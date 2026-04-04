"""Model command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..utils.config import get_config_manager, get_global_config


MODELS = {
    "default": "Default model (local)",
    "claude-3-opus": "Claude 3 Opus",
    "claude-3-sonnet": "Claude 3 Sonnet",
    "claude-3-haiku": "Claude 3 Haiku",
    "gpt-4": "GPT-4",
    "gpt-3.5-turbo": "GPT-3.5 Turbo"
}


async def model_command(args: list[str], context: CommandContext) -> str:
    """Handle /model command."""
    if not args:
        # Show current model
        config = get_global_config()
        current = config.default_model
        
        lines = [f"Current model: {current}", "", "Available models:"]
        for name, desc in MODELS.items():
            marker = " *" if name == current else ""
            lines.append(f"  {name}: {desc}{marker}")
        
        lines.extend([
            "",
            f"Base URL: {config.base_url}",
        ])
        
        return "\n".join(lines)
    
    action = args[0]
    
    if action == "set":
        if len(args) < 2:
            return "Usage: /model set <model_name>"
        
        model_name = args[1]
        
        config = get_global_config()
        config.default_model = model_name
        get_config_manager().save_global_config(config)
        
        return f"Model set to: {model_name}"
    
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


register_command(CommandHandler(
    name="model",
    description="Manage model settings",
    handler=model_command
))
