"""History command implementation."""

import os
import json
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext

HISTORY_FILE = os.path.expanduser("~/.local/share/pilotcode/history.json")


def ensure_history_dir():
    """Ensure history directory exists."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)


def load_history():
    """Load command history."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return []


def save_history(history):
    """Save command history."""
    ensure_history_dir()
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


async def history_command(args: list[str], context: CommandContext) -> str:
    """Handle /history command."""
    history = load_history()

    if not args:
        # Show recent history
        if not history:
            return "No history"

        lines = ["Command history:", ""]
        for i, entry in enumerate(history[-20:], 1):
            cmd = entry.get("command", "unknown")
            time = entry.get("time", "unknown")
            lines.append(f"  {i}. [{time}] {cmd[:60]}")

        return "\n".join(lines)

    action = args[0]

    if action == "clear":
        save_history([])
        return "History cleared"

    elif action == "search":
        if len(args) < 2:
            return "Usage: /history search <query>"

        query = args[1].lower()
        matches = [e for e in history if query in e.get("command", "").lower()]

        if not matches:
            return f"No matches for '{query}'"

        lines = [f"Matches for '{query}':", ""]
        for entry in matches[-10:]:
            cmd = entry.get("command", "unknown")
            time = entry.get("time", "unknown")
            lines.append(f"  [{time}] {cmd[:60]}")

        return "\n".join(lines)

    else:
        return f"Unknown action: {action}. Use: clear, search"


def add_to_history(command: str):
    """Add command to history."""
    history = load_history()
    history.append({"command": command, "time": datetime.now().isoformat(), "cwd": os.getcwd()})
    # Keep last 1000 commands
    history = history[-1000:]
    save_history(history)


register_command(
    CommandHandler(
        name="history",
        description="Show command history",
        handler=history_command,
        aliases=["hist"],
    )
)
