"""Share command implementation."""

import json
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


async def share_command(args: list[str], context: CommandContext) -> str:
    """Handle /share command."""
    # This would generate a shareable link or export
    # For now, create a share file

    share_data = {
        "version": "0.2.0",
        "shared_at": datetime.now().isoformat(),
        "cwd": context.cwd,
        "type": "session_share",
    }

    share_file = f"share_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    try:
        with open(share_file, "w") as f:
            json.dump(share_data, f, indent=2)

        return f"Session share file created: {share_file}\n\nNote: Full sharing functionality would upload to cloud service."
    except Exception as e:
        return f"Failed to create share: {e}"


register_command(CommandHandler(name="share", description="Share session", handler=share_command))
