"""Status bar for displaying app status."""

from textual.widgets import Static
from textual.reactive import reactive


class StatusBar(Static):
    """Status bar showing current app state."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        text-style: none;
    }
    StatusBar .status-left {
        width: 1fr;
        content-align: left middle;
    }
    StatusBar .status-center {
        width: 1fr;
        content-align: center middle;
    }
    StatusBar .status-right {
        width: 1fr;
        content-align: right middle;
    }
    StatusBar.processing {
        background: $primary 20%;
    }
    """

    status_text: reactive[str] = reactive("")
    is_processing: reactive[bool] = reactive(False)
    token_count: reactive[int] = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._left_text = ""
        self._center_text = ""
        self._right_text = ""

    def watch_is_processing(self, processing: bool):
        """React to processing state changes."""
        self.set_class(processing, "processing")
        self._update_display()

    def watch_token_count(self, count: int):
        """React to token count changes."""
        self._update_display()

    def watch_status_text(self, text: str):
        """React to status text changes."""
        self._center_text = text
        self._update_display()

    def set_status(self, text: str):
        """Set status text."""
        self.status_text = text

    def set_processing(self, processing: bool):
        """Set processing state."""
        self.is_processing = processing

    def set_token_count(self, count: int):
        """Set token count."""
        self.token_count = count

    def _update_display(self):
        """Update the display."""
        left = self._get_left_text()
        center = self._center_text or self._get_center_text()
        right = self._get_right_text()

        self.update(f"{left} {center} {right}")

    def _get_left_text(self) -> str:
        """Get left status text."""
        if self.is_processing:
            return "⏳ Processing..."
        return "✓ Ready"

    def _get_center_text(self) -> str:
        """Get center status text."""
        return ""

    def _get_right_text(self) -> str:
        """Get right status text."""
        parts = []
        if self.token_count > 0:
            parts.append(f"📊 {self.token_count} tokens")
        parts.append("/help for commands")
        return " | ".join(parts)

    def compose(self):
        """Compose the status bar."""
        self._update_display()
        # StatusBar is a Static widget, so we don't yield children
        return []
