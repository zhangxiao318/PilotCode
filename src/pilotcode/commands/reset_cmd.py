"""Reset command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def reset_command(args: list[str], context: CommandContext) -> str:
    """Handle /reset command."""
    if not args:
        return "Usage: /reset [--soft|--mixed|--hard] <commit|HEAD~n>"
    
    # Check for mode flag
    mode = "--mixed"
    target = None
    
    for arg in args:
        if arg in ("--soft", "--mixed", "--hard"):
            mode = arg
        elif not arg.startswith("-"):
            target = arg
    
    if not target:
        target = "HEAD"
    
    try:
        result = subprocess.run(
            ["git", "reset", mode, target],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            return f"Reset ({mode}) to {target}:\n{result.stdout or 'Done'}"
        else:
            return f"Error: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="reset",
    description="Reset git state",
    handler=reset_command
))
