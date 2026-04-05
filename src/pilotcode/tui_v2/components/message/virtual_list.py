"""Virtual scrolling message list for handling large conversation histories."""

from typing import Optional, Callable
from textual.widgets import Static
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.message import Message
from rich.console import RenderableType
from rich.text import Text
from rich.panel import Panel

from pilotcode.tui_v2.controller.controller import UIMessage, MessageType
from pilotcode.tui_v2.components.message.display import MessageDisplay


class VirtualMessageList(ScrollableContainer):
    """Virtual scrolling message list that only renders visible messages.
    
    This component handles large conversation histories efficiently by only
    rendering messages that are currently visible in the viewport.
    """
    
    DEFAULT_CSS = """
    VirtualMessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0 0 1 0;
        background: $background;
        color: $text;
        overflow-y: auto;
    }
    
    VirtualMessageList > .virtual-scroll-container {
        width: 100%;
        height: auto;
    }
    
    VirtualMessageList > .scroll-indicator {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        text-align: center;
        text-style: dim;
    }
    """
    
    # Reactive properties
    total_messages: reactive[int] = reactive(0)
    visible_start: reactive[int] = reactive(0)
    visible_end: reactive[int] = reactive(0)
    
    def __init__(
        self,
        buffer_size: int = 5,  # Extra messages to render above/below viewport
        estimated_height: int = 3,  # Estimated message height in lines
        **kwargs
    ):
        super().__init__(**kwargs)
        self._all_messages: list[UIMessage] = []  # All messages storage
        self._rendered_displays: dict[int, MessageDisplay] = {}  # Currently rendered
        self._buffer_size = buffer_size
        self._estimated_height = estimated_height
        self._streaming_message_id: Optional[int] = None
        self._scroll_to_bottom_on_update = False
        
    def compose(self):
        """Compose the virtual list."""
        with Vertical(classes="virtual-scroll-container"):
            pass  # Messages will be added dynamically
    
    def on_mount(self):
        """Called when widget is mounted."""
        self._update_virtual_window()
    
    def add_message(self, message: UIMessage) -> Optional[MessageDisplay]:
        """Add a message to the list.
        
        Returns the display widget if it was rendered, None otherwise.
        """
        message_id = len(self._all_messages)
        self._all_messages.append(message)
        self.total_messages = len(self._all_messages)
        
        # Handle streaming updates
        if message.is_streaming:
            self._streaming_message_id = message_id
        elif self._streaming_message_id == message_id:
            # Streaming completed
            self._streaming_message_id = None
        
        # Check if message should be rendered (in visible window)
        if self._should_render(message_id):
            display = self._render_message(message_id, message)
            # Auto-scroll if at bottom
            if message_id == len(self._all_messages) - 1:
                self._scroll_to_bottom_on_update = True
            return display
        
        return None
    
    def update_streaming_message(self, content: str) -> bool:
        """Update the currently streaming message."""
        if self._streaming_message_id is None:
            return False
        
        if self._streaming_message_id in self._rendered_displays:
            display = self._rendered_displays[self._streaming_message_id]
            if display.message:
                display.message.content = content
                display.refresh()
                return True
        return False
    
    def _should_render(self, message_id: int) -> bool:
        """Check if a message should be rendered based on current viewport."""
        return self.visible_start - self._buffer_size <= message_id <= self.visible_end + self._buffer_size
    
    def _render_message(self, message_id: int, message: UIMessage) -> MessageDisplay:
        """Render a message and add it to the container."""
        display = MessageDisplay(message)
        self._rendered_displays[message_id] = display
        
        # Mount the display
        container = self.query_one(".virtual-scroll-container", Vertical)
        container.mount(display)
        
        return display
    
    def _update_virtual_window(self):
        """Update which messages are rendered based on scroll position."""
        if not self._all_messages:
            return
        
        # Calculate visible range based on scroll position
        viewport_height = self.size.height if self.size.height else 20
        scroll_y = self.scroll_offset.y if self.scroll_offset else 0
        
        # Estimate which messages are visible
        # This is a simplified calculation - in production, you'd measure actual heights
        estimated_visible = viewport_height // self._estimated_height
        start_idx = max(0, scroll_y // self._estimated_height - self._buffer_size)
        end_idx = min(len(self._all_messages), start_idx + estimated_visible + self._buffer_size * 2)
        
        # Update reactive properties
        self.visible_start = start_idx
        self.visible_end = end_idx
        
        # Remove messages outside the window
        to_remove = []
        for msg_id in self._rendered_displays:
            if msg_id < start_idx or msg_id > end_idx:
                to_remove.append(msg_id)
        
        container = self.query_one(".virtual-scroll-container", Vertical)
        for msg_id in to_remove:
            display = self._rendered_displays.pop(msg_id)
            display.remove()
        
        # Add messages inside the window that aren't rendered
        for msg_id in range(start_idx, end_idx):
            if msg_id not in self._rendered_displays and msg_id < len(self._all_messages):
                self._render_message(msg_id, self._all_messages[msg_id])
    
    def on_scroll(self):
        """Handle scroll events to update virtual window."""
        self._update_virtual_window()
    
    def watch_scroll_offset(self, offset):
        """React to scroll offset changes."""
        self._update_virtual_window()
    
    def clear_messages(self) -> None:
        """Clear all messages."""
        # Remove all rendered displays
        container = self.query_one(".virtual-scroll-container", Vertical)
        for display in self._rendered_displays.values():
            display.remove()
        self._rendered_displays.clear()
        self._all_messages.clear()
        self.total_messages = 0
        self._streaming_message_id = None
        self.visible_start = 0
        self.visible_end = 0
    
    def scroll_to_bottom(self, animate: bool = False) -> None:
        """Scroll to the bottom of the message list."""
        if self._all_messages:
            # Render last few messages if not already rendered
            last_idx = len(self._all_messages) - 1
            if last_idx not in self._rendered_displays:
                for i in range(max(0, last_idx - self._buffer_size), last_idx + 1):
                    if i not in self._rendered_displays:
                        self._render_message(i, self._all_messages[i])
            
            self.scroll_end(animate=animate)
    
    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self._all_messages)
    
    def get_rendered_count(self) -> int:
        """Get count of currently rendered messages."""
        return len(self._rendered_displays)
    
    def render(self) -> RenderableType:
        """Render the virtual list with a scroll indicator."""
        # Update virtual window on render
        self.call_after_refresh(self._update_virtual_window)
        
        # Scroll to bottom if needed
        if self._scroll_to_bottom_on_update:
            self._scroll_to_bottom_on_update = False
            self.call_after_refresh(self.scroll_to_bottom)
        
        return super().render()


class HybridMessageList(ScrollableContainer):
    """Hybrid message list that uses virtual scrolling for large histories.
    
    For small histories (< 100 messages), renders all messages.
    For large histories, switches to virtual scrolling mode.
    """
    
    DEFAULT_CSS = """
    HybridMessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0 0 1 0;
        background: $background;
        color: $text;
    }
    """
    
    # Threshold to switch to virtual scrolling
    VIRTUAL_THRESHOLD = 100
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._messages: list[UIMessage] = []
        self._displays: list[MessageDisplay] = []
        self._streaming_message: Optional[MessageDisplay] = None
        self._pending_tool: Optional[UIMessage] = None
        self._use_virtual = False
        self._virtual_list: Optional[VirtualMessageList] = None
        self._simple_list: Optional[Vertical] = None
    
    def compose(self):
        """Compose the hybrid list."""
        # Start with simple list
        self._simple_list = Vertical()
        self._simple_list.add_class("simple-list")
        yield self._simple_list
    
    def add_message(self, message: UIMessage) -> Optional[MessageDisplay]:
        """Add a message to the list."""
        self._messages.append(message)
        
        # Check if we need to switch to virtual mode
        if len(self._messages) > self.VIRTUAL_THRESHOLD and not self._use_virtual:
            self._switch_to_virtual_mode()
        
        if self._use_virtual and self._virtual_list:
            return self._virtual_list.add_message(message)
        else:
            return self._add_to_simple_list(message)
    
    def _add_to_simple_list(self, message: UIMessage) -> MessageDisplay:
        """Add message to simple (non-virtual) list."""
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
                return self._displays[-1]
        
        # Create new message display
        display = MessageDisplay(message)
        self._displays.append(display)
        if self._simple_list:
            self._simple_list.mount(display)
        
        if message.is_streaming:
            self._streaming_message = display
        
        # Scroll to bottom
        def scroll_to_bottom():
            self.scroll_end(animate=False)
        self.call_after_refresh(scroll_to_bottom)
        
        return display
    
    def _switch_to_virtual_mode(self):
        """Switch from simple to virtual mode."""
        self._use_virtual = True
        
        # Create virtual list
        self._virtual_list = VirtualMessageList()
        
        # Remove simple list
        if self._simple_list:
            self._simple_list.remove()
            self._simple_list = None
        
        # Mount virtual list
        self.mount(self._virtual_list)
        
        # Migrate existing messages
        for msg in self._messages:
            self._virtual_list.add_message(msg)
    
    def update_last_message(self, message: UIMessage) -> bool:
        """Update the last message."""
        if not self._messages:
            return False
        
        self._messages[-1] = message
        
        if self._use_virtual and self._virtual_list:
            # Virtual list handles updates via streaming mechanism
            if message.is_streaming:
                return self._virtual_list.update_streaming_message(message.content)
        elif self._displays:
            self._displays[-1].message = message
            return True
        
        return False
    
    def clear_messages(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        
        if self._use_virtual and self._virtual_list:
            self._virtual_list.clear_messages()
        elif self._simple_list:
            for display in self._displays:
                display.remove()
            self._displays.clear()
        
        self._streaming_message = None
        self._pending_tool = None
    
    def scroll_to_bottom(self, animate: bool = False) -> None:
        """Scroll to bottom."""
        if self._use_virtual and self._virtual_list:
            self._virtual_list.scroll_to_bottom(animate=animate)
        else:
            self.scroll_end(animate=animate)
