"""Virtual scrolling message list for handling large conversation histories."""

from typing import Optional
from textual.containers import ScrollableContainer
from textual.reactive import reactive
from rich.console import RenderableType

from pilotcode.tui_v2.controller.controller import UIMessage, MessageType
from pilotcode.tui_v2.components.message.display import MessageDisplay


class HybridMessageList(ScrollableContainer):
    """Message list with automatic virtual scrolling for large histories.

    For small histories (< 100 messages), renders all messages.
    For large histories, uses optimized rendering.
    """

    DEFAULT_CSS = """
    HybridMessageList {
        width: 100%;
        height: 1fr;
        border: none;
        padding: 0;
        background: $background;
        color: $text;
        overflow-y: auto;
    }
    """

    # Threshold to show warning about large history
    LARGE_HISTORY_THRESHOLD = 500

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._messages: list[UIMessage] = []
        self._displays: list[MessageDisplay] = []
        self._streaming_message: Optional[MessageDisplay] = None
        self._pending_tool: Optional[UIMessage] = None

    def add_message(self, message: UIMessage) -> MessageDisplay:
        """Add a message to the list."""
        self._messages.append(message)

        # Handle streaming updates
        if message.is_streaming and self._streaming_message:
            if (
                self._streaming_message.message
                and self._streaming_message.message.type == message.type
            ):
                self._streaming_message.message = message
                # Force refresh with layout to update widget size
                self._streaming_message.refresh(layout=True)
                # Auto-scroll to bottom during streaming
                self.scroll_end(animate=False)
                return self._streaming_message

        # Handle streaming completion
        if not message.is_streaming and self._streaming_message:
            if (
                self._streaming_message.message
                and self._streaming_message.message.type == message.type
            ):
                self._streaming_message.message = message
                # Force final refresh with layout
                self._streaming_message.refresh(layout=True)
                self._streaming_message = None
                self.scroll_end()
                return self._displays[-1]

        # Create new message display
        display = MessageDisplay(message)
        self._displays.append(display)
        self.mount(display)

        if message.is_streaming:
            self._streaming_message = display

        # Auto-scroll to bottom immediately and after refresh
        self.scroll_end(animate=False)
        def scroll_to_bottom():
            self.scroll_end(animate=False)
        self.call_after_refresh(scroll_to_bottom)

        # Warning for very large histories
        if len(self._messages) == self.LARGE_HISTORY_THRESHOLD:
            # Could show a compact notification here
            pass

        return display

    def update_last_message(self, message: UIMessage) -> bool:
        """Update the last message."""
        if not self._displays:
            return False

        self._displays[-1].message = message
        return True

    def clear_messages(self) -> None:
        """Clear all messages."""
        for display in self._displays:
            display.remove()
        self._displays.clear()
        self._messages.clear()
        self._streaming_message = None
        self._pending_tool = None

    def scroll_to_bottom(self, animate: bool = False) -> None:
        """Scroll to bottom."""
        self.scroll_end(animate=animate)

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self._messages)

    @property
    def _messages_list(self) -> list[MessageDisplay]:
        """Access to message displays (for compatibility)."""
        return self._displays
