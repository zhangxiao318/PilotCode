"""Enhanced prompt input with history and autocomplete."""

from typing import Optional, Callable
from pathlib import Path

from textual.widgets import Static, TextArea
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.message import Message


class PromptInput(TextArea):
    """Enhanced input with history and @file support."""
    
    DEFAULT_CSS = """
    PromptInput {
        height: 4;
        min-height: 1;
        max-height: 10;
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
    /* Ensure text is visible */
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
            placeholder="Type message...",
            show_line_numbers=False,
            soft_wrap=True,
            **kwargs
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
        
        # History navigation with Up/Down (when at start of input)
        if key == "up":
            if self.cursor_at_start_of_text:
                event.prevent_default()
                self._show_previous_history()
            return
        
        if key == "down":
            if self.cursor_at_end_of_text:
                event.prevent_default()
                self._show_next_history()
            return
        
        # Submit on Enter (Ctrl+Enter for newline is handled by TextArea)
        if key == "enter":
            event.prevent_default()
            event.stop()
            self._submit()
            return
        
        # Handle @ for file references
        if key == "@":
            # Could trigger file autocomplete popup here
            pass
    
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
        lines = self.text.split('\n')
        pos = sum(len(lines[i]) + 1 for i in range(row)) + col
        return pos
    
    @cursor_position.setter
    def cursor_position(self, pos: int):
        """Set cursor position."""
        # Convert absolute position to (row, col)
        lines = self.text.split('\n')
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
        lines = self.text.split('\n')
        if not lines:
            return True
        row, col = self.cursor_location
        return row == len(lines) - 1 and col == len(lines[-1])
    
    def parse_file_references(self, text: str) -> tuple[str, list[str]]:
        """Parse @file references from text.
        
        Returns:
            (cleaned_text, list_of_file_paths)
        """
        import re
        
        # Pattern to match @file or @"file with spaces"
        pattern = r'@("([^"]*)"|(\S+))'
        
        files = []
        def replace_match(match):
            # Get the file path (group 2 for quoted, group 3 for unquoted)
            path = match.group(2) or match.group(3)
            files.append(path)
            return f"[File: {path}]"  # Replace with readable format
        
        cleaned = re.sub(pattern, replace_match, text)
        return cleaned, files


class PromptWithMode(Horizontal):
    """Prompt input with > indicator."""
    
    DEFAULT_CSS = """
    PromptWithMode {
        height: 4;
        background: $surface;
        border-top: solid $border;
    }
    PromptWithMode Static {
        width: 2;
        height: 100%;
        padding: 0 0 0 1;
        content-align: left top;
        background: $surface;
        color: $primary;
        text-style: bold;
    }
    PromptWithMode PromptInput {
        width: 1fr;
        height: 100%;
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
    
    def compose(self):
        """Compose the widget."""
        yield Static(">")  # Prompt indicator
        yield self.input
    
    def on_prompt_input_submitted(self, event: PromptInput.Submitted):
        """Forward input submission to parent."""
        # Forward the event
        self.post_message(self.Submitted(event.text))
    
    @property
    def prompt_input(self) -> PromptInput:
        """Get the prompt input widget."""
        return self.input
