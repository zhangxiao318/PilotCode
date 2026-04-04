"""Session command implementation."""

import json
import os
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


# Session storage
SESSIONS_DIR = os.path.expanduser("~/.local/share/pilotcode/sessions")


def ensure_sessions_dir():
    """Ensure sessions directory exists."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def get_session_file(session_id: str) -> str:
    """Get path to session file."""
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


async def session_command(args: list[str], context: CommandContext) -> str:
    """Handle /session command."""
    ensure_sessions_dir()
    
    if not args:
        # List sessions
        sessions = []
        for filename in os.listdir(SESSIONS_DIR):
            if filename.endswith('.json'):
                session_id = filename[:-5]
                filepath = os.path.join(SESSIONS_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    sessions.append({
                        "id": session_id,
                        "name": data.get("name", "Unnamed"),
                        "created": data.get("created", "Unknown"),
                        "message_count": len(data.get("messages", []))
                    })
                except:
                    pass
        
        if not sessions:
            return "No saved sessions"
        
        lines = ["Saved sessions:", ""]
        for s in sorted(sessions, key=lambda x: x["created"], reverse=True):
            lines.append(f"  {s['id']}: {s['name']} ({s['message_count']} messages)")
        return "\n".join(lines)
    
    action = args[0]
    
    if action == "save":
        name = args[1] if len(args) > 1 else f"Session {datetime.now().isoformat()}"
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        session_data = {
            "name": name,
            "created": datetime.now().isoformat(),
            "cwd": context.cwd,
            "messages": []  # Would get from query engine
        }
        
        with open(get_session_file(session_id), 'w') as f:
            json.dump(session_data, f, indent=2)
        
        return f"Session saved: {session_id}"
    
    elif action == "load":
        if len(args) < 2:
            return "Usage: /session load <session_id>"
        
        session_id = args[1]
        filepath = get_session_file(session_id)
        
        if not os.path.exists(filepath):
            return f"Session not found: {session_id}"
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return f"Loaded session: {data.get('name', session_id)}"
    
    elif action == "delete":
        if len(args) < 2:
            return "Usage: /session delete <session_id>"
        
        session_id = args[1]
        filepath = get_session_file(session_id)
        
        if not os.path.exists(filepath):
            return f"Session not found: {session_id}"
        
        os.remove(filepath)
        return f"Deleted session: {session_id}"
    
    else:
        return f"Unknown action: {action}. Use: save, load, delete"


register_command(CommandHandler(
    name="session",
    description="Manage sessions",
    handler=session_command,
    aliases=["sessions"]
))
