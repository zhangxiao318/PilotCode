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
    session_id: reactive[str] = reactive("")
    context_window: reactive[int] = reactive(0)
    max_output_tokens: reactive[int] = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._left_text = ""
        self._center_text = ""
        self._right_text = ""
        self._session_id = ""

    def watch_is_processing(self, processing: bool):
        """React to processing state changes."""
        self.set_class(processing, "processing")
        self._update_display()

    def watch_token_count(self, count: int):
        """React to token count changes."""
        self._update_display()

    def watch_context_window(self, ctx: int):
        """React to context window changes."""
        self._update_display()

    def watch_max_output_tokens(self, max_out: int):
        """React to max output tokens changes."""
        self._update_display()

    def watch_status_text(self, text: str):
        """React to status text changes."""
        self._center_text = text
        self._update_display()

    def watch_session_id(self, sid: str):
        """React to session ID changes."""
        self._session_id = sid
        self._update_display()

    def set_session_id(self, sid: str):
        """Set session ID."""
        self.session_id = sid

    def set_status(self, text: str):
        """Set status text."""
        self.status_text = text

    def set_processing(self, processing: bool):
        """Set processing state."""
        self.is_processing = processing

    def set_token_count(self, count: int):
        """Set token count."""
        self.token_count = count

    def set_context_info(self, context_window: int, max_output_tokens: int):
        """Set context window info for display."""
        self.context_window = context_window
        self.max_output_tokens = max_output_tokens

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
        """Get right status text.

        OpenCode-style context usage: "context: 56.3% (147.5k/262.1k)"
        """
        parts = []
        if self._session_id:
            parts.append(f"📝 {self._session_id}")

        # Context usage display
        if self.context_window > 0 and self.token_count > 0:
            usable = max(1, self.context_window - self.max_output_tokens)
            pct = min(100.0, self.token_count / usable * 100)
            current_str = self._fmt_k(self.token_count)
            usable_str = self._fmt_k(usable)
            parts.append(f"context: {pct:.1f}% ({current_str}/{usable_str})")

        parts.append("/help for commands")
        return " | ".join(parts)

    @staticmethod
    def _fmt_k(n: int) -> str:
        """Format number as k/m suffix (e.g. 147500 -> '147.5k')."""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}m"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    def compose(self):
        """Compose the status bar."""
        self._update_display()
        # StatusBar is a Static widget, so we don't yield children
        return []
