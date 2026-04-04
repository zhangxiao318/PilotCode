"""Theme command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..utils.config import get_config_manager, get_global_config


THEMES = {
    "default": "Default color scheme",
    "dark": "Dark theme with high contrast",
    "light": "Light theme",
    "monokai": "Monokai color scheme",
    "dracula": "Dracula color scheme",
    "solarized": "Solarized color scheme"
}


async def theme_command(args: list[str], context: CommandContext) -> str:
    """Handle /theme command."""
    if not args:
        # Show current theme
        config = get_global_config()
        current = getattr(config, 'theme', 'default')
        
        lines = [f"Current theme: {current}", "", "Available themes:"]
        for name, desc in THEMES.items():
            marker = " *" if name == current else ""
            lines.append(f"  {name}: {desc}{marker}")
        
        return "\n".join(lines)
    
    theme_name = args[0]
    
    if theme_name == "list":
        lines = ["Available themes:"]
        for name, desc in THEMES.items():
            lines.append(f"  {name}: {desc}")
        return "\n".join(lines)
    
    if theme_name not in THEMES:
        return f"Unknown theme: {theme_name}. Use: list"
    
    # Set theme
    config = get_global_config()
    config.theme = theme_name
    get_config_manager().save_global_config(config)
    
    return f"Theme set to: {theme_name}"


register_command(CommandHandler(
    name="theme",
    description="Change color theme",
    handler=theme_command
))
