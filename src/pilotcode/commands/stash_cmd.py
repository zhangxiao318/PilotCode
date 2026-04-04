"""Stash command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def stash_command(args: list[str], context: CommandContext) -> str:
    """Handle /stash command."""
    if not args:
        # Show stash list
        try:
            result = subprocess.run(
                ["git", "stash", "list"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                if result.stdout.strip():
                    return f"Stash list:\n{result.stdout}"
                else:
                    return "No stashes"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    action = args[0]
    
    if action == "save":
        message = " ".join(args[1:]) if len(args) > 1 else "WIP"
        
        try:
            result = subprocess.run(
                ["git", "stash", "save", message],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Stashed: {message}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "pop":
        try:
            result = subprocess.run(
                ["git", "stash", "pop"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Stash popped:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "apply":
        try:
            result = subprocess.run(
                ["git", "stash", "apply"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return f"Stash applied:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "drop":
        try:
            result = subprocess.run(
                ["git", "stash", "drop"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return "Stash dropped"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "clear":
        try:
            result = subprocess.run(
                ["git", "stash", "clear"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            
            if result.returncode == 0:
                return "All stashes cleared"
            else:
                return f"Error: {result.stderr}"
        
        except Exception as e:
            return f"Error: {e}"
    
    else:
        return f"Unknown action: {action}. Use: save, pop, apply, drop, clear"


register_command(CommandHandler(
    name="stash",
    description="Git stash operations",
    handler=stash_command
))
