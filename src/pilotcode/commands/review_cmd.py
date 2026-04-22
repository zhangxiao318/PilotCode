"""Review command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def review_command(args: list[str], context: CommandContext) -> str:
    """Handle /review command."""
    if not args:
        # Show diff for review
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0 and result.stdout:
                diff = result.stdout[:3000]
                if len(result.stdout) > 3000:
                    diff += "\n... (truncated)"

                return f"Changes to review:\n```diff\n{diff}\n```\n\nUse /review approve or /review comments"

            # Check unstaged changes
            result = subprocess.run(
                ["git", "diff"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0 and result.stdout:
                return "Unstaged changes found. Stage with: git add"

            return "No changes to review"

        except Exception as e:
            return f"Error: {e}"

    action = args[0]

    if action == "approve":
        return "Changes approved (conceptually). Use /commit to commit."

    elif action == "comments":
        if len(args) < 2:
            return "Usage: /review comments <your comments>"

        comments = " ".join(args[1:])
        return f"Review comments recorded: {comments}"

    elif action == "request":
        return "Code review requested (placeholder - would integrate with PR system)"

    else:
        return f"Unknown action: {action}. Use: approve, comments, request"


register_command(
    CommandHandler(
        name="review", description="Code review helper", handler=review_command, aliases=["cr"]
    )
)
