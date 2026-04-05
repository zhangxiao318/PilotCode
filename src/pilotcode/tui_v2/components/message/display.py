"""Message display components for chat interface."""

from typing import Optional
from textual.widgets import Static
from textual.containers import Vertical, ScrollableContainer
from textual.reactive import reactive
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from pilotcode.tui_v2.controller.controller import UIMessage, MessageType


class MessageDisplay(Static):
    """Display a single message."""
    
    DEFAULT_CSS = """
    MessageDisplay {
        height: auto;
        margin: 0 0 1 0;
        padding: 0;
    }
    MessageDisplay.user {
        background: $primary 10%;
        border-left: solid $primary;
    }
    MessageDisplay.assistant {
        background: $surface;
        border-left: solid $secondary;
    }
    MessageDisplay.tool {
        background: $warning 10%;
        border-left: solid $warning;
    }
    MessageDisplay.error {
        background: $error 10%;
        border-left: solid $error;
    }
    MessageDisplay.system {
        background: $surface-darken-1;
        border-left: solid #888888;
        color: #888888;
    }
    MessageDisplay .message-header {
        color: $text-muted;
        text-style: bold;
        margin-bottom: 1;
    }
    MessageDisplay .message-content {
        padding: 0 1;
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
        for cls in ["user", "assistant", "tool", "error", "system"]:
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
            MessageType.TOOL_RESULT: "tool",
            MessageType.ERROR: "error",
            MessageType.SYSTEM: "system",
        }
        return mapping.get(msg_type, "")
    
    def _get_header(self) -> str:
        """Get message header."""
        if not self.message:
            return ""
        
        headers = {
            MessageType.USER: "You",
            MessageType.ASSISTANT: "🤖 Assistant",
            MessageType.TOOL_USE: "🔧 Tool",
            MessageType.TOOL_RESULT: "📤 Result",
            MessageType.ERROR: "❌ Error",
            MessageType.SYSTEM: "ℹ️  System",
        }
        
        header = headers.get(self.message.type, "Unknown")
        
        # Add tool name if available
        if self.message.type in (MessageType.TOOL_USE, MessageType.TOOL_RESULT):
            tool_name = self.message.metadata.get("tool_name", "")
            if tool_name:
                header += f": {tool_name}"
            
            # Add safety indicator for tool use
            if self.message.type == MessageType.TOOL_USE:
                is_safe = self.message.metadata.get("is_safe", False)
                if is_safe:
                    header += " ✓ (safe)"
                else:
                    header += " ⚠ (confirm)"
        
        return header
    
    def render(self) -> RenderableType:
        """Render the message."""
        if not self.message:
            return ""
        
        header = self._get_header()
        content = self.message.content
        
        # Format content based on type
        if self.message.type == MessageType.ASSISTANT:
            # Render markdown for assistant messages
            try:
                content_obj = Markdown(content)
            except Exception:
                content_obj = Text(content)
        else:
            content_obj = Text(content)
        
        # Show streaming indicator
        if self.message.is_streaming:
            header += " ▌"  # Blinking cursor
        
        return Panel(
            content_obj,
            title=header,
            title_align="left",
            border_style="none",
            padding=(0, 1)
        )
    
    def watch_message(self, message: UIMessage):
        """React to message changes."""
        self._update_classes()
        self.refresh()


class MessageList(ScrollableContainer):
    """Scrollable list of messages."""
    
    DEFAULT_CSS = """
    MessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0 1;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._messages: list[MessageDisplay] = []
        self._streaming_message: Optional[MessageDisplay] = None
    
    def add_message(self, message: UIMessage) -> MessageDisplay:
        """Add a message to the list.
        
        If the message is streaming, it will be updated in place.
        """
        # Check if we're updating an existing streaming message
        if message.is_streaming and self._streaming_message:
            if (self._streaming_message.message and 
                self._streaming_message.message.type == message.type):
                # Update existing
                self._streaming_message.message = message
                return self._streaming_message
        
        # Check if a streaming message is now complete
        if not message.is_streaming and self._streaming_message:
            if (self._streaming_message.message and 
                self._streaming_message.message.type == message.type):
                # Complete the streaming message
                self._streaming_message.message = message
                self._streaming_message = None
                self.scroll_end()
                return self._messages[-1]
        
        # Create new message display
        display = MessageDisplay(message)
        self._messages.append(display)
        self.mount(display)
        
        if message.is_streaming:
            self._streaming_message = display
        
        # Scroll to bottom after message is mounted
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
    
    def clear_messages(self):
        """Clear all messages."""
        for display in self._messages:
            display.remove()
        self._messages.clear()
        self._streaming_message = None
    
    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self._messages)
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the list."""
        self.scroll_end()
