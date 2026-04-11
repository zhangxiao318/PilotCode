"""Export command implementation."""

import json
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


async def export_command(args: list[str], context: CommandContext) -> str:
    """Handle /export command."""
    if not args:
        return "Usage: /export <filename>"

    filename = args[0]

    # Add .json extension if not present
    if not filename.endswith(".json"):
        filename += ".json"

    # Build export data
    export_data = {
        "version": "0.2.0",
        "exported_at": datetime.now().isoformat(),
        "cwd": context.cwd,
        "messages": [],  # Would get from query engine
        "config": {},
    }

    try:
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=2)

        return f"Session exported to: {filename}"

    except Exception as e:
        return f"Export failed: {e}"


register_command(
    CommandHandler(name="export", description="Export session to file", handler=export_command)
)
