"""Session command implementation with full persistence support."""

import os
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext
from ..services.session_persistence import (
    get_session_persistence,
    save_session as persist_save_session,
    load_session as persist_load_session,
    list_sessions as persist_list_sessions,
)


async def session_command(args: list[str], context: CommandContext) -> str:
    """Handle /session command."""
    persistence = get_session_persistence()

    if not args or args[0] == "list":
        # List sessions
        project_path = context.cwd if context else None
        sessions = persist_list_sessions(project_path)

        if not sessions:
            return "No saved sessions"

        lines = ["Saved sessions:", ""]
        for s in sessions:
            project_info = f" (project: {s.project_path})" if s.project_path else ""
            lines.append(f"  {s.session_id}: {s.name} ({s.message_count} messages){project_info}")
        return "\n".join(lines)

    action = args[0]

    if action == "save":
        name = args[1] if len(args) > 1 else f"Session {datetime.now().isoformat()[:19]}"

        # Generate session ID
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Get messages from context if available
        messages = []
        if context and hasattr(context, "messages"):
            messages = context.messages

        # Save session
        success = persist_save_session(
            session_id=session_id,
            messages=messages,
            name=name,
            project_path=context.cwd if context else None,
        )

        if success:
            return f"Session saved: {session_id} - {name}"
        else:
            return "Failed to save session"

    elif action == "load":
        if len(args) < 2:
            return "Usage: /session load <session_id>"

        session_id = args[1]
        result = persist_load_session(session_id)

        if result is None:
            return f"Session not found: {session_id}"

        messages, metadata = result

        # Would load messages into current session here
        # For now, just show info
        return f"Loaded session: {metadata.get('name', session_id)} ({len(messages)} messages)"

    elif action == "delete":
        if len(args) < 2:
            return "Usage: /session delete <session_id>"

        session_id = args[1]
        success = persistence.delete_session(session_id)

        if success:
            return f"Deleted session: {session_id}"
        else:
            return f"Session not found: {session_id}"

    elif action == "rename":
        if len(args) < 3:
            return "Usage: /session rename <session_id> <new_name>"

        session_id = args[1]
        new_name = " ".join(args[2:])
        success = persistence.rename_session(session_id, new_name)

        if success:
            return f"Renamed session to: {new_name}"
        else:
            return f"Session not found: {session_id}"

    elif action == "export":
        if len(args) < 3:
            return "Usage: /session export <session_id> <format> [path]"

        session_id = args[1]
        fmt = args[2]
        export_path = args[3] if len(args) > 3 else f"{session_id}.{fmt}"

        from pathlib import Path

        success = persistence.export_session(session_id, Path(export_path), fmt)

        if success:
            return f"Exported session to: {export_path}"
        else:
            return f"Failed to export session: {session_id}"

    elif action == "info":
        if len(args) < 2:
            return "Usage: /session info <session_id>"

        session_id = args[1]
        result = persist_load_session(session_id)

        if result is None:
            return f"Session not found: {session_id}"

        messages, metadata = result

        lines = [
            f"Session: {metadata.get('name', session_id)}",
            f"ID: {session_id}",
            f"Created: {metadata.get('created_at', 'Unknown')}",
            f"Updated: {metadata.get('updated_at', 'Unknown')}",
            f"Messages: {len(messages)}",
        ]

        if metadata.get("project_path"):
            lines.append(f"Project: {metadata['project_path']}")

        if metadata.get("summary"):
            lines.append(f"Summary: {metadata['summary'][:100]}...")

        if metadata.get("tags"):
            lines.append(f"Tags: {', '.join(metadata['tags'])}")

        return "\n".join(lines)

    else:
        return f"Unknown action: {action}. Use: save, load, delete, rename, export, info, list"


register_command(
    CommandHandler(
        name="session",
        description="Manage sessions with full persistence",
        handler=session_command,
        aliases=["sessions"],
    )
)
