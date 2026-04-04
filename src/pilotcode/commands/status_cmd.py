"""Status command implementation."""

import subprocess
import os
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


async def status_command(args: list[str], context: CommandContext) -> str:
    """Handle /status command."""
    lines = ["PilotCode Status", "=" * 40, ""]
    
    # Git status
    try:
        result = subprocess.run(
            ["git", "status", "-sb"],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            lines.append("Git:")
            for line in result.stdout.strip().split('\n')[:5]:
                lines.append(f"  {line}")
            lines.append("")
    except:
        pass
    
    # Current directory
    lines.append(f"Working directory: {context.cwd}")
    lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Configuration
    from ..utils.config import get_global_config
    config = get_global_config()
    lines.append(f"Model: {config.default_model}")
    lines.append(f"Theme: {config.theme}")
    
    return "\n".join(lines)


register_command(CommandHandler(
    name="status",
    description="Show status information",
    handler=status_command,
    aliases=["st"]
))
