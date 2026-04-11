"""Session context management for maintaining project-wide state.

This module provides:
1. Project-level context tracking (what we're working on)
2. Key information extraction and maintenance
3. Context summarization for LLM
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProjectContext:
    """Project-level context maintained across the session."""

    name: str = ""  # e.g., "博客系统"
    description: str = ""  # Brief description of the project
    type: str = ""  # e.g., "web_app", "cli_tool", "library"
    key_files: list[str] = field(default_factory=list)  # Important files
    tech_stack: list[str] = field(default_factory=list)  # e.g., ["Python", "Django"]
    current_focus: str = ""  # Current task/focus
    completed_tasks: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)

    def to_summary(self) -> str:
        """Generate a summary string for LLM context."""
        parts = []
        if self.name:
            parts.append(f"Project: {self.name}")
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.type:
            parts.append(f"Type: {self.type}")
        if self.tech_stack:
            parts.append(f"Tech Stack: {', '.join(self.tech_stack)}")
        if self.key_files:
            parts.append(f"Key Files: {', '.join(self.key_files)}")
        if self.current_focus:
            parts.append(f"Current Focus: {self.current_focus}")
        if self.pending_tasks:
            parts.append(f"Pending Tasks: {', '.join(self.pending_tasks)}")
        if self.completed_tasks:
            parts.append(f"Completed: {', '.join(self.completed_tasks[-3:])}")  # Last 3

        return "\n".join(parts) if parts else "No project context established yet."

    def update_from_conversation(self, user_message: str, assistant_response: str):
        """Try to extract project context from conversation.

        This is called periodically to update project context based on
        what the user and assistant are discussing.
        """
        # Simple heuristic extraction (can be enhanced with LLM)
        msg_lower = user_message.lower()

        # Detect project creation/initialization
        if any(
            phrase in msg_lower
            for phrase in ["创建一个", "创建", "新建", "new project", "create a"]
        ):
            if not self.name:
                # Try to extract project name
                import re

                # Match patterns like "创建一个博客系统" or "create a blog system"
                patterns = [
                    r"创建[一个]*([^，。]+?)(系统|应用|项目|app|system)",
                    r"create\s+a[n]?\s+(\w+\s*)+(system|app|project)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, user_message, re.IGNORECASE)
                    if match:
                        self.name = (
                            match.group(0).replace("创建一个", "").replace("create a ", "").strip()
                        )
                        break

        # Detect tech stack mentions
        tech_keywords = {
            "python": "Python",
            "django": "Django",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "react": "React",
            "vue": "Vue",
            "node": "Node.js",
            "express": "Express",
            "go": "Go",
            "golang": "Go",
            "rust": "Rust",
            "java": "Java",
            "spring": "Spring",
        }
        for keyword, tech in tech_keywords.items():
            if keyword in msg_lower and tech not in self.tech_stack:
                self.tech_stack.append(tech)

        # Update current focus based on recent messages
        if any(word in msg_lower for word in ["测试", "test", "debug", "bug", "fix"]):
            self.current_focus = "Testing and debugging"
        elif any(word in msg_lower for word in ["添加", "增加", "实现", "add", "implement"]):
            self.current_focus = "Adding new features"
        elif any(word in msg_lower for word in ["优化", "改进", "重构", "optimize", "refactor"]):
            self.current_focus = "Optimization and refactoring"


@dataclass
class SessionContext:
    """Complete session context including project info and conversation metadata."""

    project: ProjectContext = field(default_factory=ProjectContext)
    session_start: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    total_tokens: int = 0
    last_compressed_at: int = 0  # Message count when last compressed

    def to_system_message(self) -> str:
        """Generate system message with current context."""
        parts = ["=== Current Session Context ==="]
        parts.append(self.project.to_summary())
        parts.append(f"\nSession started: {self.session_start.strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"Messages in session: {self.message_count}")
        if self.total_tokens > 0:
            parts.append(f"Estimated tokens: {self.total_tokens}")
        parts.append("=== End Context ===")
        return "\n".join(parts)

    def should_compress(self, threshold_messages: int = 20) -> bool:
        """Check if context should be compressed."""
        return (self.message_count - self.last_compressed_at) > threshold_messages

    def record_compression(self):
        """Record that compression happened."""
        self.last_compressed_at = self.message_count

    def update_stats(self, new_messages: int, tokens: int):
        """Update session statistics."""
        self.message_count += new_messages
        self.total_tokens += tokens


class SessionContextManager:
    """Manages session context throughout the conversation."""

    def __init__(self):
        self.context = SessionContext()
        self._extraction_counter = 0

    def get_system_prompt_addition(self) -> str:
        """Get additional context to add to system prompt."""
        return self.context.to_system_message()

    def update_from_message(self, user_message: str, assistant_response: str):
        """Update context from a message pair."""
        self._extraction_counter += 1

        # Extract context every 3 messages (not every message to save computation)
        if self._extraction_counter % 3 == 0:
            self.context.project.update_from_conversation(user_message, assistant_response)

        # Update stats
        self.context.update_stats(2, 0)  # 2 messages, tokens estimated elsewhere

    def set_project_info(self, name: str = "", description: str = "", type: str = ""):
        """Manually set project information."""
        if name:
            self.context.project.name = name
        if description:
            self.context.project.description = description
        if type:
            self.context.project.type = type

    def add_key_file(self, filepath: str):
        """Add a key file to track."""
        if filepath not in self.context.project.key_files:
            self.context.project.key_files.append(filepath)

    def add_completed_task(self, task: str):
        """Mark a task as completed."""
        if task not in self.context.project.completed_tasks:
            self.context.project.completed_tasks.append(task)
        # Remove from pending if present
        if task in self.context.project.pending_tasks:
            self.context.project.pending_tasks.remove(task)

    def add_pending_task(self, task: str):
        """Add a pending task."""
        if task not in self.context.project.pending_tasks:
            self.context.project.pending_tasks.append(task)

    def set_current_focus(self, focus: str):
        """Set current focus/task."""
        self.context.project.current_focus = focus

    def should_compress_context(self, message_count: int, threshold: int = 20) -> bool:
        """Check if we should compress the conversation context."""
        return message_count > threshold and self.context.should_compress(threshold)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "project": {
                "name": self.context.project.name,
                "description": self.context.project.description,
                "type": self.context.project.type,
                "key_files": self.context.project.key_files,
                "tech_stack": self.context.project.tech_stack,
                "current_focus": self.context.project.current_focus,
                "completed_tasks": self.context.project.completed_tasks,
                "pending_tasks": self.context.project.pending_tasks,
            },
            "session_start": self.context.session_start.isoformat(),
            "message_count": self.context.message_count,
            "total_tokens": self.context.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionContextManager":
        """Deserialize from dictionary."""
        manager = cls()
        proj_data = data.get("project", {})
        manager.context.project.name = proj_data.get("name", "")
        manager.context.project.description = proj_data.get("description", "")
        manager.context.project.type = proj_data.get("type", "")
        manager.context.project.key_files = proj_data.get("key_files", [])
        manager.context.project.tech_stack = proj_data.get("tech_stack", [])
        manager.context.project.current_focus = proj_data.get("current_focus", "")
        manager.context.project.completed_tasks = proj_data.get("completed_tasks", [])
        manager.context.project.pending_tasks = proj_data.get("pending_tasks", [])

        if "session_start" in data:
            manager.context.session_start = datetime.fromisoformat(data["session_start"])
        manager.context.message_count = data.get("message_count", 0)
        manager.context.total_tokens = data.get("total_tokens", 0)

        return manager


# Global instance
_session_context_manager: SessionContextManager | None = None


def get_session_context_manager() -> SessionContextManager:
    """Get global session context manager."""
    global _session_context_manager
    if _session_context_manager is None:
        _session_context_manager = SessionContextManager()
    return _session_context_manager


def reset_session_context():
    """Reset session context (e.g., on /clear)."""
    global _session_context_manager
    _session_context_manager = SessionContextManager()
