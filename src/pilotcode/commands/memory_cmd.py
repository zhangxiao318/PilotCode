"""Memory command implementation."""

import os
import json
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext

MEMORY_DIR = os.path.expanduser("~/.local/share/pilotcode/memory")


def ensure_memory_dir():
    """Ensure memory directory exists."""
    os.makedirs(MEMORY_DIR, exist_ok=True)


async def memory_command(args: list[str], context: CommandContext) -> str:
    """Handle /memory command."""
    ensure_memory_dir()

    if not args:
        # List memories
        files = []
        for filename in os.listdir(MEMORY_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(MEMORY_DIR, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    files.append((filename[:-5], data.get("created", "Unknown")))
                except:
                    pass

        if not files:
            return "No memories stored"

        lines = ["Stored memories:", ""]
        for name, created in sorted(files, key=lambda x: x[1], reverse=True):
            lines.append(f"  {name}: {created}")
        return "\n".join(lines)

    action = args[0]

    if action == "add":
        if len(args) < 3:
            return "Usage: /memory add <name> <content>"

        name = args[1]
        content = " ".join(args[2:])

        filepath = os.path.join(MEMORY_DIR, f"{name}.json")
        data = {"content": content, "created": datetime.now().isoformat(), "context": context.cwd}

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return f"Memory added: {name}"

    elif action == "get":
        if len(args) < 2:
            return "Usage: /memory get <name>"

        name = args[1]
        filepath = os.path.join(MEMORY_DIR, f"{name}.json")

        if not os.path.exists(filepath):
            return f"Memory not found: {name}"

        with open(filepath, "r") as f:
            data = json.load(f)

        return f"Memory: {name}\n\n{data.get('content', '')}"

    elif action == "delete":
        if len(args) < 2:
            return "Usage: /memory delete <name>"

        name = args[1]
        filepath = os.path.join(MEMORY_DIR, f"{name}.json")

        if not os.path.exists(filepath):
            return f"Memory not found: {name}"

        os.remove(filepath)
        return f"Memory deleted: {name}"

    else:
        return f"Unknown action: {action}. Use: add, get, delete"


register_command(
    CommandHandler(name="memory", description="Manage memories", handler=memory_command)
)
