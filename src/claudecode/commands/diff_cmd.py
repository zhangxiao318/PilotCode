"""Diff command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def diff_command(args: list[str], context: CommandContext) -> str:
    """Handle /diff command."""
    try:
        cmd = ["git", "diff"]
        
        if args:
            # Specific file or options
            cmd.extend(args)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        
        if not result.stdout:
            return "No changes"
        
        # Format as markdown code block
        diff = result.stdout[:5000]  # Limit size
        if len(result.stdout) > 5000:
            diff += "\n... (truncated)"
        
        return f"```diff\n{diff}\n```"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="diff",
    description="Show git diff",
    handler=diff_command
))
