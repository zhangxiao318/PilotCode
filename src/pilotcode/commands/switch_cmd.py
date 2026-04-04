"""Switch command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def switch_command(args: list[str], context: CommandContext) -> str:
    """Handle /switch command."""
    if not args:
        return "Usage: /switch <branch> | /switch -c <new_branch>"
    
    create_new = "-c" in args or "--create" in args
    
    if create_new:
        # Find branch name
        branch = None
        for i, arg in enumerate(args):
            if arg in ("-c", "--create"):
                if i + 1 < len(args):
                    branch = args[i + 1]
                break
        
        if not branch:
            return "Usage: /switch -c <new_branch>"
        
        try:
            result = subprocess.run(
                ["git", "switch", "-c", branch],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Created and switched to branch: {branch}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    else:
        branch = args[0]
        
        try:
            result = subprocess.run(
                ["git", "switch", branch],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Switched to branch: {branch}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(
    name="switch",
    description="Switch branch (modern git)",
    handler=switch_command
))
