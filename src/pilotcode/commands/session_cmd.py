"""Session command implementation with full persistence support."""

from datetime import datetime
from .base import CommandHandler, register_command, CommandContext
from ..services.session_persistence import (
    get_session_persistence,
    save_session as persist_save_session,
    load_session as persist_load_session,
    list_sessions as persist_list_sessions,
)


def _display_width(text: str) -> int:
    """Calculate display width considering CJK characters (2 cols each)."""
    try:
        import wcwidth

        return wcwidth.wcswidth(text) or len(text)
    except Exception:
        return len(text)


def _pad(text: str, width: int) -> str:
    """Pad text to exact display width, accounting for CJK chars."""
    w = _display_width(text)
    if w >= width:
        return text
    return text + " " * (width - w)


async def session_command(args: list[str], context: CommandContext) -> str:
    """Handle /session command."""
    persistence = get_session_persistence()

    if not args or args[0] == "list":
        # List sessions
        # Default: list ALL sessions regardless of project path.
        # Only filter by cwd when explicitly requested via "list here".
        project_path = context.cwd if context and len(args) > 1 and args[1] == "here" else None
        sessions = persist_list_sessions(project_path)

        if not sessions:
            return "No saved sessions"

        # Build a fixed-width text table for clean TUI display
        lines: list[str] = []
        lines.append(
            _pad("Session ID", 23) + _pad("Messages", 9) + _pad("Project Path", 31) + "Summary"
        )
        lines.append("━" * 84)
        for s in sessions:
            sid = _pad(s.session_id[:22], 23)
            msg = _pad(str(s.message_count), 9)
            path = _pad((s.project_path or "—")[:29], 31)
            summary = (s.summary or "—")[:34]
            lines.append(f"{sid}{msg}{path}{summary}")
        return "\n".join(lines)

    action = args[0]

    if action == "save":
        name = args[1] if len(args) > 1 else f"Session {datetime.now().isoformat()[:19]}"

        # Use the current session ID if available; otherwise generate one
        session_id = (
            context.session_id
            if context and context.session_id
            else datetime.now().strftime("%Y%m%d_%H%M%S")
        )

        # Get messages from the query_engine in context
        messages = []
        if context and context.query_engine and hasattr(context.query_engine, "messages"):
            messages = context.query_engine.messages

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
