"""Cherrypick command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def cherrypick_command(args: list[str], context: CommandContext) -> str:
    """Handle /cherrypick command."""
    if not args:
        return "Usage: /cherrypick <commit> | /cherrypick --continue | /cherrypick --abort"
    
    action = args[0]
    
    if action in ("--continue", "--abort", "--quit"):
        # Cherry-pick control
        try:
            result = subprocess.run(
                ["git", "cherry-pick", action],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Cherry-pick {action}:\n{result.stdout}"
            else:
                return f"Error:\n{result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    else:
        # Cherry-pick commit
        commit = action
        
        try:
            result = subprocess.run(
                ["git", "cherry-pick", commit],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Cherry-picked {commit}:\n{result.stdout}"
            else:
                return f"Cherry-pick failed:\n{result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(
    name="cherrypick",
    description="Cherry-pick commit",
    handler=cherrypick_command
))
