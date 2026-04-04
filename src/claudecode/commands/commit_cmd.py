"""Commit command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def commit_command(args: list[str], context: CommandContext) -> str:
    """Handle /commit command."""
    if not args:
        # Show status
        try:
            result = subprocess.run(
                ["git", "status", "-sb"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Git status:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    # Commit with message
    message = " ".join(args)
    
    try:
        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            cwd=context.cwd
        )
        
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            return f"Committed: {result.stdout}"
        else:
            return f"Commit failed: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="commit",
    description="Git commit helper",
    handler=commit_command,
    aliases=["ci"]
))
