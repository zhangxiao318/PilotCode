"""Message display components for chat interface."""

from typing import Optional
from textual.widgets import Static
from textual.containers import Vertical, ScrollableContainer
from textual.reactive import reactive
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

from pilotcode.tui_v2.controller.controller import UIMessage, MessageType


class MessageDisplay(Static):
    """Display a single message with compact styling."""
    
    DEFAULT_CSS = """
    MessageDisplay {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
        background: transparent;
        color: $text;
    }
    
    /* User messages - right aligned, bubble style */
    MessageDisplay.user {
        text-align: right;
        background: transparent;
        color: $text;
        margin: 1 0;
    }
    MessageDisplay.user Static {
        background: $primary 20%;
        color: $text;
        padding: 1 2;
    }
    
    /* Assistant messages - clean text */
    MessageDisplay.assistant {
        background: transparent;
        color: $text;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    
    /* Tool messages - compact, visible */
    MessageDisplay.tool {
        background: transparent;
        color: $warning;
        padding: 0 1;
        margin: 0;
    }
    
    /* Tool result - inline with tool */
    MessageDisplay.tool-result {
        background: transparent;
        color: $success;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    
    /* Error - visible red */
    MessageDisplay.error {
        background: $error 20%;
        border-left: solid $error;
        color: $text;
        padding: 1 2;
        margin: 1 0;
    }
    
    /* System - visible but subtle */
    MessageDisplay.system {
        background: $surface;
        color: $text-muted;
        text-align: center;
        padding: 1;
        margin: 1 0;
    }
    """
    
    message: reactive[Optional[UIMessage]] = reactive(None)
    
    def __init__(self, message: UIMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._update_classes()
    
    def _update_classes(self):
        """Update CSS classes based on message type."""
        if not self.message:
            return
        
        # Remove old type classes
        for cls in ["user", "assistant", "tool", "tool-result", "error", "system"]:
            self.remove_class(cls)
        
        # Add new type class
        type_class = self._get_type_class(self.message.type)
        if type_class:
            self.add_class(type_class)
    
    def _get_type_class(self, msg_type: MessageType) -> str:
        """Get CSS class for message type."""
        mapping = {
            MessageType.USER: "user",
            MessageType.ASSISTANT: "assistant",
            MessageType.TOOL_USE: "tool",
            MessageType.TOOL_RESULT: "tool-result",
            MessageType.ERROR: "error",
            MessageType.SYSTEM: "system",
        }
        return mapping.get(msg_type, "")
    
    def _get_header(self) -> str:
        """Get message header (used for non-compact modes)."""
        if not self.message:
            return ""
        
        headers = {
            MessageType.USER: "You",
            MessageType.ASSISTANT: "🤖",
            MessageType.TOOL_USE: "🔧",
            MessageType.TOOL_RESULT: "📤",
            MessageType.ERROR: "❌",
            MessageType.SYSTEM: "ℹ️",
        }
        
        return headers.get(self.message.type, "")
    
    def _format_content(self) -> RenderableType:
        """Format content based on message type."""
        if not self.message:
            return ""
        
        content = self.message.content or ""
        
        # Tool messages - compact format
        if self.message.type == MessageType.TOOL_USE:
            tool_name = self.message.metadata.get("tool_name", "Tool")
            is_safe = self.message.metadata.get("is_safe", False)
            safe_marker = "✓" if is_safe else "⚠"
            return Text(f"{safe_marker} {tool_name}", style="dim")
        
        # Tool result - show output preview
        if self.message.type == MessageType.TOOL_RESULT:
            # Truncate long output
            lines = content.strip().split('\n')
            preview = lines[0][:80] if lines else ""
            if len(lines) > 1 or len(content) > 80:
                preview += " ..."
            return Text(f"→ {preview}", style="dim")
        
        # User messages - plain text
        if self.message.type == MessageType.USER:
            return Text(content)
        
        # Assistant messages - markdown
        if self.message.type == MessageType.ASSISTANT:
            try:
                return Markdown(content)
            except Exception:
                return Text(content)
        
        # System/Error - plain text
        return Text(content)
    
    def render(self) -> RenderableType:
        """Render the message."""
        if not self.message:
            return Text("")
        
        try:
            content = self._format_content()
            
            # User messages - right align the container
            if self.message.type == MessageType.USER:
                return Align.right(content)
            
            # All other messages - left align
            return content
        except Exception as e:
            # Fallback to plain text on any error
            return Text(f"[Render Error: {str(e)}]")
    
    def watch_message(self, message: UIMessage):
        """React to message changes."""
        self._update_classes()
        self.refresh()


class CompactToolDisplay(Static):
    """Compact display for tool execution (combines TOOL_USE and TOOL_RESULT)."""
    
    DEFAULT_CSS = """
    CompactToolDisplay {
        height: auto;
        padding: 0 2;
        margin: 0;
        color: $text-muted;
        text-style: dim;
    }
    """
    
    def __init__(self, tool_name: str, command: str, result: str, **kwargs):
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.command = command
        self.result = result
    
    def render(self) -> RenderableType:
        """Render compact tool info."""
        text = Text()
        text.append(f"$ {self.command}", style="yellow dim")
        text.append(" → ", style="dim")
        # Show result preview
        result_preview = self.result.strip().split('\n')[0][:60]
        if len(self.result) > 60 or '\n' in self.result:
            result_preview += "..."
        text.append(result_preview, style="green dim")
        return text


class MessageList(ScrollableContainer):
    """Scrollable list of messages with compact styling."""
    
    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0 0 1 0;
        background: $background;
        color: $text;
    }
    MessageList > * {
        margin: 0 0 0 0;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._messages: list[MessageDisplay] = []
        self._streaming_message: Optional[MessageDisplay] = None
        self._pending_tool: Optional[UIMessage] = None
    
    def add_message(self, message: UIMessage) -> MessageDisplay:
        """Add a message to the list."""
        # Handle streaming updates
        if message.is_streaming and self._streaming_message:
            if (self._streaming_message.message and 
                self._streaming_message.message.type == message.type):
                self._streaming_message.message = message
                return self._streaming_message
        
        # Handle streaming completion
        if not message.is_streaming and self._streaming_message:
            if (self._streaming_message.message and 
                self._streaming_message.message.type == message.type):
                self._streaming_message.message = message
                self._streaming_message = None
                self.scroll_end()
                return self._messages[-1]
        
        # Store TOOL_USE to potentially combine with result
        if message.type == MessageType.TOOL_USE:
            self._pending_tool = message
        
        # TOOL_RESULT - check if we can combine with pending tool
        if message.type == MessageType.TOOL_RESULT and self._pending_tool:
            # For now, just show both separately with compact styling
            self._pending_tool = None
        
        # Create new message display
        display = MessageDisplay(message)
        self._messages.append(display)
        self.mount(display)
        
        if message.is_streaming:
            self._streaming_message = display
        
        # Scroll to bottom
        def scroll_to_bottom():
            self.scroll_end(animate=False)
        self.call_after_refresh(scroll_to_bottom)
        return display
    
    def update_last_message(self, message: UIMessage) -> bool:
        """Update the last message."""
        if not self._messages:
            return False
        
        self._messages[-1].message = message
        return True
    
    def clear_messages(self) -> None:
        """Clear all messages from the list."""
        # Remove all message displays
        for display in self._messages:
            display.remove()
        self._messages.clear()
        self._streaming_message = None
        self._pending_tool = None
