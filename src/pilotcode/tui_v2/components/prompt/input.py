"""Enhanced prompt input with history, autocomplete and syntax highlighting."""

import re
from typing import Optional

from textual.widgets import Static, TextArea
from textual.containers import Horizontal, Vertical
from textual.message import Message


class PromptInput(TextArea):
    """Enhanced input with history, @file support and syntax highlighting."""

    DEFAULT_CSS = """
    PromptInput {
        height: 3;
        border: none;
        padding: 0 1;
        background: $surface;
        color: $text;
    }
    PromptInput:focus {
        border: none;
    }
    PromptInput .text-area--placeholder {
        color: $text-muted;
    }
    PromptInput .text-area--cursor {
        background: $primary;
    }
    PromptInput .text-area--gutter {
        background: $surface;
        color: $text-muted;
        width: 2;
    }
    PromptInput .text-area--content {
        color: $text;
    }
    PromptInput .text-area--line {
        color: $text;
    }
    """

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, text: str):
            self.text = text
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="Type message... (@file, /command)",
            show_line_numbers=False,
            soft_wrap=True,
            **kwargs,
        )
        self._input_history: list[str] = []
        self._input_history_index = -1
        self._current_input = ""

    def on_mount(self):
        """Called when widget is mounted."""
        self.focus()

    def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key

        # History navigation with Up/Down (when at start/end of input)
        if key == "up":
            if self.cursor_at_start_of_text:
                event.prevent_default()
                event.stop()
                self._show_previous_history()
            return

        if key == "down":
            if self.cursor_at_end_of_text:
                event.prevent_default()
                event.stop()
                self._show_next_history()
            return

        # Submit on Enter
        if key == "enter":
            event.prevent_default()
            event.stop()
            self._submit()
            return

    def _submit(self) -> None:
        """Submit the current input."""
        text = self.text.strip()
        if not text:
            return

        # Add to history
        if not self._input_history or self._input_history[-1] != text:
            self._input_history.append(text)
        self._input_history_index = -1

        # Emit submit event
        self.post_message(self.Submitted(text))

        # Clear input
        self.text = ""
        self._current_input = ""

    def _show_previous_history(self) -> None:
        """Show previous history item."""
        if not self._input_history:
            return

        # Save current if at start
        if self._input_history_index == -1:
            self._current_input = self.text

        self._input_history_index = min(self._input_history_index + 1, len(self._input_history) - 1)
        if self._input_history_index >= 0:
            self.text = self._input_history[-(self._input_history_index + 1)]
            self.cursor_position = len(self.text)

    def _show_next_history(self) -> None:
        """Show next history item."""
        if self._input_history_index <= 0:
            self._input_history_index = -1
            self.text = self._current_input
        else:
            self._input_history_index -= 1
            self.text = self._input_history[-(self._input_history_index + 1)]
        self.cursor_position = len(self.text)

    @property
    def cursor_position(self) -> int:
        """Get cursor position."""
        # TextArea has cursor location as (row, col)
        row, col = self.cursor_location
        lines = self.text.split("\n")
        pos = sum(len(lines[i]) + 1 for i in range(row)) + col
        return pos

    @cursor_position.setter
    def cursor_position(self, pos: int):
        """Set cursor position."""
        # Convert absolute position to (row, col)
        lines = self.text.split("\n")
        row = 0
        remaining = pos
        while row < len(lines) and remaining > len(lines[row]):
            remaining -= len(lines[row]) + 1  # +1 for newline
            row += 1
        col = max(0, min(remaining, len(lines[row]) if row < len(lines) else 0))
        self.cursor_location = (row, col)

    @property
    def cursor_at_start_of_text(self) -> bool:
        """Check if cursor is at start of input."""
        return self.cursor_location == (0, 0)

    @property
    def cursor_at_end_of_text(self) -> bool:
        """Check if cursor is at end of input."""
        lines = self.text.split("\n")
        if not lines:
            return True
        row, col = self.cursor_location
        return row == len(lines) - 1 and col == len(lines[-1])

    def parse_file_references(self, text: str) -> tuple[str, list[str]]:
        """Parse @file references from text.

        Returns:
            (cleaned_text, list_of_file_paths)
        """
        # Pattern to match @file or @"file with spaces"
        pattern = r'(@"([^"]*)"|@(\S+))'

        files = []

        def replace_match(match):
            # Get the file path (group 2 for quoted, group 3 for unquoted)
            path = match.group(2) or match.group(3)
            if path:
                files.append(path)
            return f"[File: {path}]"  # Replace with readable format

        cleaned = re.sub(pattern, replace_match, text)
        return cleaned, files

    def get_file_references(self, text: str) -> list[str]:
        """Extract file references from text."""
        _, files = self.parse_file_references(text)
        return files

    def get_command(self, text: str) -> Optional[str]:
        """Extract command from text if it starts with /."""
        text = text.strip()
        if text.startswith("/"):
            parts = text.split()
            if parts:
                return parts[0][1:]  # Remove leading /
        return None


class PromptWithMode(Vertical):
    """Prompt input with > indicator and syntax highlighting status."""

    DEFAULT_CSS = """
    PromptWithMode {
        height: auto;
        min-height: 3;
        background: $surface;
    }
    PromptWithMode Horizontal {
        height: 3;
    }
    PromptWithMode Static.prompt-indicator {
        width: 2;
        height: 3;
        padding: 0 0 0 1;
        content-align: center middle;
        background: $surface;
        color: $primary;
        text-style: bold;
    }
    PromptWithMode PromptInput {
        width: 1fr;
        height: 3;
        background: $surface;
        color: $text;
    }
    PromptWithMode Static.syntax-status {
        width: 100%;
        height: auto;
        background: $surface;
        color: $text-muted;
        text-style: dim;
        padding: 0 1;
    }
    PromptWithMode Static.syntax-status.has-refs {
        color: $success;
    }
    """

    class Submitted(Message):
        """Message sent when input is submitted."""

        def __init__(self, text: str):
            self.text = text
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.input = PromptInput()
        self._syntax_status: Optional[Static] = None

    def compose(self):
        """Compose the widget."""
        with Horizontal():
            yield Static(">", classes="prompt-indicator")  # Prompt indicator
            yield self.input
        self._syntax_status = Static("", classes="syntax-status")
        yield self._syntax_status

    def on_mount(self):
        """Called when widget is mounted."""
        self.input.focus()

    def on_prompt_input_submitted(self, event: PromptInput.Submitted):
        """Forward input submission to parent."""
        # Clear syntax status on submit
        if self._syntax_status:
            self._syntax_status.update("")
            self._syntax_status.remove_class("has-refs")
        # Forward the event
        self.post_message(self.Submitted(event.text))

    def on_input_changed(self, event) -> None:
        """Handle input changes from child TextArea."""
        # Update syntax status
        self._update_syntax_status(self.input.text)

    def _update_syntax_status(self, text: str):
        """Update syntax highlighting status display."""
        if not self._syntax_status:
            return

        # Parse file references
        files = self.input.get_file_references(text)
        command = self.input.get_command(text)

        status_parts = []
        if command:
            status_parts.append(f"📋 /{command}")
        if files:
            status_parts.append(f"📎 {len(files)} file(s)")

        if status_parts:
            self._syntax_status.update(" | ".join(status_parts))
            self._syntax_status.add_class("has-refs")
        else:
            self._syntax_status.update("")
            self._syntax_status.remove_class("has-refs")

    @property
    def prompt_input(self) -> PromptInput:
        """Get the prompt input widget."""
        return self.input

    @property
    def text(self) -> str:
        """Get input text."""
        return self.input.text

    @text.setter
    def text(self, value: str):
        """Set input text."""
        self.input.text = value
        self._update_syntax_status(value)
