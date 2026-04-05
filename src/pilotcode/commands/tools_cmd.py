"""Tools command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..tools.registry import get_all_tools


async def tools_command(args: list[str], context: CommandContext) -> str:
    """Handle /tools command."""
    tools = get_all_tools()
    
    if not args:
        # List all tools
        lines = [f"Available tools ({len(tools)}):", ""]
        
        for tool in sorted(tools, key=lambda t: t.name):
            aliases = f" ({', '.join(tool.aliases)})" if tool.aliases else ""
            # Safely check read_only and concurrency status
            try:
                readonly = " [RO]" if tool.is_read_only(None) else ""
            except (AttributeError, TypeError):
                readonly = ""
            try:
                concurrent = " [C]" if tool.is_concurrency_safe(None) else ""
            except (AttributeError, TypeError):
                concurrent = ""
            
            desc = tool.description
            if callable(desc):
                desc = tool.name
            
            lines.append(f"  {tool.name}{aliases}{readonly}{concurrent}")
            lines.append(f"    {desc[:60]}...")
        
        return "\n".join(lines)
    
    search_term = args[0].lower()
    
    # Search tools
    matches = []
    for tool in tools:
        if (search_term in tool.name.lower() or 
            any(search_term in a.lower() for a in tool.aliases) or
            search_term in tool.search_hint.lower()):
            matches.append(tool)
    
    if not matches:
        return f"No tools matching '{search_term}'"
    
    lines = [f"Matching tools ({len(matches)}):", ""]
    for tool in matches:
        lines.append(f"  {tool.name}: {tool.search_hint}")
    
    return "\n".join(lines)


register_command(CommandHandler(
    name="tools",
    description="List available tools",
    handler=tools_command
))
