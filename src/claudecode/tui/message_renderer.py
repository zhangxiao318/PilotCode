"""Message rendering for TUI."""

from enum import Enum
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.tree import Tree
from rich.style import Style


class MessageType(Enum):
    """Types of messages."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Message:
    """Message for rendering."""
    role: MessageType
    content: str
    metadata: dict[str, Any] | None = None
    timestamp: str | None = None


class MessageRenderer:
    """Renderer for chat messages."""
    
    # Message type styles
    STYLES = {
        MessageType.USER: {
            "border": "blue",
            "prefix": "You",
            "icon": "👤",
        },
        MessageType.ASSISTANT: {
            "border": "green",
            "prefix": "Claude",
            "icon": "🤖",
        },
        MessageType.SYSTEM: {
            "border": "dim",
            "prefix": "System",
            "icon": "⚙️",
        },
        MessageType.TOOL_USE: {
            "border": "yellow",
            "prefix": "Tool",
            "icon": "🔧",
        },
        MessageType.TOOL_RESULT: {
            "border": "cyan",
            "prefix": "Result",
            "icon": "✓",
        },
        MessageType.ERROR: {
            "border": "red",
            "prefix": "Error",
            "icon": "❌",
        },
        MessageType.WARNING: {
            "border": "yellow",
            "prefix": "Warning",
            "icon": "⚠️",
        },
        MessageType.INFO: {
            "border": "blue",
            "prefix": "Info",
            "icon": "ℹ️",
        },
    }
    
    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._show_tool_calls = True
        self._show_timestamps = False
        self._max_content_length = 10000
    
    def set_show_tool_calls(self, show: bool):
        """Toggle tool call visibility."""
        self._show_tool_calls = show
    
    def set_show_timestamps(self, show: bool):
        """Toggle timestamp visibility."""
        self._show_timestamps = show
    
    def render(self, message: Message) -> Panel:
        """Render a message as a panel."""
        style = self.STYLES.get(message.role, self.STYLES[MessageType.SYSTEM])
        
        # Build title
        title_parts = [f"{style['icon']} {style['prefix']}"]
        if self._show_timestamps and message.timestamp:
            title_parts.append(f"[{message.timestamp}]")
        
        title = " ".join(title_parts)
        
        # Render content based on type
        if message.role == MessageType.TOOL_USE:
            content = self._render_tool_use(message)
        elif message.role == MessageType.TOOL_RESULT:
            content = self._render_tool_result(message)
        elif message.role == MessageType.ERROR:
            content = self._render_error(message)
        else:
            content = self._render_markdown(message.content)
        
        return Panel(
            content,
            title=title,
            border_style=style["border"],
            padding=(1, 2),
        )
    
    def _render_markdown(self, content: str) -> Markdown:
        """Render markdown content."""
        # Truncate if too long
        if len(content) > self._max_content_length:
            content = content[:self._max_content_length] + "\n\n[Content truncated...]"
        
        return Markdown(content)
    
    def _render_tool_use(self, message: Message) -> Text:
        """Render tool use message."""
        if not self._show_tool_calls:
            return Text("[Tool call hidden]", style="dim")
        
        metadata = message.metadata or {}
        tool_name = metadata.get("tool_name", "unknown")
        tool_input = metadata.get("tool_input", {})
        
        text = Text()
        text.append(f"Using tool: ", style="bold")
        text.append(f"{tool_name}\n", style="cyan")
        
        if tool_input:
            text.append("\nInput:\n", style="dim")
            import json
            input_str = json.dumps(tool_input, indent=2, ensure_ascii=False)
            text.append(input_str[:500], style="dim")
            if len(input_str) > 500:
                text.append("\n...", style="dim")
        
        return text
    
    def _render_tool_result(self, message: Message) -> Text:
        """Render tool result message."""
        if not self._show_tool_calls:
            return Text("[Tool result hidden]", style="dim")
        
        metadata = message.metadata or {}
        success = metadata.get("success", True)
        
        text = Text()
        
        if success:
            text.append("✓ ", style="green")
            text.append("Success\n", style="green")
        else:
            text.append("✗ ", style="red")
            text.append("Failed\n", style="red")
        
        # Show result content
        content = message.content
        if len(content) > 1000:
            content = content[:1000] + "\n\n[Result truncated...]"
        
        text.append("\n" + content, style="white")
        
        return text
    
    def _render_error(self, message: Message) -> Text:
        """Render error message."""
        text = Text()
        text.append("❌ Error\n\n", style="bold red")
        text.append(message.content, style="red")
        return text
    
    def render_code_block(
        self,
        code: str,
        language: str | None = None,
        filename: str | None = None,
    ) -> Panel:
        """Render a code block with syntax highlighting."""
        syntax = Syntax(
            code,
            language or "text",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        
        title = filename or f"Code ({language or 'text'})"
        
        return Panel(
            syntax,
            title=f"📄 {title}",
            border_style="cyan",
        )
    
    def render_file_tree(
        self,
        files: list[str],
        root_name: str = ".",
    ) -> Tree:
        """Render file tree."""
        tree = Tree(f"📁 {root_name}")
        
        for file_path in sorted(files):
            parts = file_path.split("/")
            current = tree
            
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # File
                    icon = self._get_file_icon(part)
                    current.add(f"{icon} {part}")
                else:
                    # Directory
                    current = current.add(f"📁 {part}")
        
        return tree
    
    def _get_file_icon(self, filename: str) -> str:
        """Get icon for file type."""
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        
        icons = {
            "py": "🐍",
            "js": "📜",
            "ts": "📘",
            "json": "📋",
            "md": "📝",
            "txt": "📄",
            "yml": "⚙️",
            "yaml": "⚙️",
            "toml": "⚙️",
            "rs": "🦀",
            "go": "🐹",
            "java": "☕",
            "cpp": "⚡",
            "c": "⚡",
            "h": "📚",
            "html": "🌐",
            "css": "🎨",
            "sql": "🗄️",
            "sh": "🔧",
            "dockerfile": "🐳",
        }
        
        return icons.get(ext, "📄")
    
    def render_diff(
        self,
        old: str,
        new: str,
        old_label: str = "Old",
        new_label: str = "New",
    ) -> Panel:
        """Render a diff view."""
        from difflib import unified_diff
        
        diff_lines = list(unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=old_label,
            tofile=new_label,
        ))
        
        text = Text()
        for line in diff_lines:
            if line.startswith("+"):
                text.append(line, style="green")
            elif line.startswith("-"):
                text.append(line, style="red")
            elif line.startswith("@"):
                text.append(line, style="cyan")
            else:
                text.append(line, style="dim")
        
        return Panel(
            text,
            title="📝 Diff",
            border_style="yellow",
        )
    
    def render_compact(
        self,
        message: Message,
        max_width: int = 80,
    ) -> Text:
        """Render message in compact form."""
        style = self.STYLES.get(message.role, self.STYLES[MessageType.SYSTEM])
        
        text = Text()
        text.append(f"{style['icon']} ", style=style["border"])
        
        # Truncate content
        content = message.content.replace("\n", " ")[:max_width - 10]
        text.append(content, style="white")
        
        if len(message.content) > max_width - 10:
            text.append("...", style="dim")
        
        return text
    
    def render_system_message(self, content: str, level: str = "info") -> Panel:
        """Render system message."""
        styles = {
            "info": ("ℹ️", "blue"),
            "success": ("✅", "green"),
            "warning": ("⚠️", "yellow"),
            "error": ("❌", "red"),
        }
        
        icon, color = styles.get(level, styles["info"])
        
        return Panel(
            Text(content),
            title=f"{icon} System",
            border_style=color,
        )


# Global renderer
_renderer: MessageRenderer | None = None


def get_message_renderer() -> MessageRenderer:
    """Get global message renderer."""
    global _renderer
    if _renderer is None:
        _renderer = MessageRenderer()
    return _renderer
