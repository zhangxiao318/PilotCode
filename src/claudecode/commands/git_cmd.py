"""Git command implementation."""

import subprocess
import os
from .base import CommandHandler, register_command, CommandContext


async def git_command(args: list[str], context: CommandContext) -> str:
    """Handle /git command."""
    if not args:
        # Show git status
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
                return f"Not a git repository or error: {result.stderr}"
        except Exception as e:
            return f"Error: {e}"
    
    action = args[0]
    
    if action == "commit":
        if len(args) < 2:
            return "Usage: /git commit <message>"
        
        message = " ".join(args[1:])
        
        # Stage all and commit
        try:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True,
                cwd=context.cwd
            )
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
    
    elif action == "diff":
        try:
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            if result.returncode == 0:
                if result.stdout:
                    # Limit output
                    diff = result.stdout[:2000]
                    if len(result.stdout) > 2000:
                        diff += "\n... (truncated)"
                    return f"```diff\n{diff}\n```"
                else:
                    return "No changes"
            else:
                return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "log":
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            if result.returncode == 0:
                return f"Recent commits:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {e}"
    
    elif action == "branch":
        try:
            result = subprocess.run(
                ["git", "branch"],
                capture_output=True,
                text=True,
                cwd=context.cwd
            )
            if result.returncode == 0:
                return f"Branches:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error: {e}"
    
    else:
        return f"Unknown action: {action}. Use: commit, diff, log, branch"


register_command(CommandHandler(
    name="git",
    description="Git operations",
    handler=git_command,
    aliases=["g"]
))
