"""Unicode-aware input widgets for proper CJK and multi-byte character support."""

from __future__ import annotations

from textual.widgets import Input, TextArea
from textual.events import Key


class UnicodeInput(Input):
    """Input widget with proper Unicode character handling.
    
    Fixes issues where backspace deletes partial multi-byte characters
    or deletes entire words instead of single characters.
    """
    
    def _delete_character_left(self) -> None:
        """Delete one Unicode character to the left of cursor."""
        if self.cursor_position <= 0:
            return
        
        # Get text before cursor
        text_before = self.value[:self.cursor_position]
        
        if not text_before:
            return
        
        # Remove last Unicode character (properly handle multi-byte chars)
        # In Python, slicing strings handles Unicode correctly
        new_text_before = text_before[:-1]
        
        # Reconstruct value
        self.value = new_text_before + self.value[self.cursor_position:]
        self.cursor_position = len(new_text_before)
    
    def _delete_word_left(self) -> None:
        """Delete one word to the left (Ctrl+Backspace behavior)."""
        if self.cursor_position <= 0:
            return
        
        text_before = self.value[:self.cursor_position]
        
        # Find the start of the current word
        # A word boundary is: space, punctuation, or CJK character
        import re
        
        # Pattern matches word characters at the end
        match = re.search(r'(\S+)$', text_before)
        if match:
            # Delete the word
            word_start = len(text_before) - len(match.group(1))
            new_text_before = text_before[:word_start]
        else:
            # Just delete trailing whitespace/single char
            new_text_before = text_before[:-1] if text_before else ""
        
        self.value = new_text_before + self.value[self.cursor_position:]
        self.cursor_position = len(new_text_before)
    
    def on_key(self, event: Key) -> None:
        """Handle key events with proper Unicode support."""
        key = event.key
        
        # Handle backspace - delete single Unicode character
        if key == "backspace":
            event.stop()
            self._delete_character_left()
            return
        
        # Handle Ctrl+Backspace - delete word
        if key == "ctrl+backspace" or key == "ctrl+h":
            event.stop()
            self._delete_word_left()
            return
        
        # Handle Ctrl+W (common terminal word delete)
        if key == "ctrl+w":
            event.stop()
            self._delete_word_left()
            return
        
        # Let other keys pass through to parent class
        super().on_key(event)


class UnicodeTextArea(TextArea):
    """TextArea with proper Unicode character handling for multi-line input."""
    
    def _delete_character_left(self) -> None:
        """Delete one Unicode character to the left of cursor."""
        text = self.text
        cursor = self.cursor_location
        
        if cursor is None:
            return
        
        row, col = cursor
        
        if col > 0:
            # Delete character at current position in current line
            lines = text.split('\n')
            if row < len(lines):
                line = lines[row]
                if col <= len(line):
                    # Remove one Unicode character
                    new_line = line[:col-1] + line[col:]
                    lines[row] = new_line
                    self.text = '\n'.join(lines)
                    self.cursor_location = (row, col - 1)
        elif row > 0:
            # At start of line, join with previous line
            lines = text.split('\n')
            if row < len(lines):
                prev_line_len = len(lines[row - 1])
                lines[row - 1] = lines[row - 1] + lines[row]
                lines.pop(row)
                self.text = '\n'.join(lines)
                self.cursor_location = (row - 1, prev_line_len)
    
    def _delete_word_left(self) -> None:
        """Delete one word to the left."""
        text = self.text
        cursor = self.cursor_location
        
        if cursor is None:
            return
        
        row, col = cursor
        lines = text.split('\n')
        
        if row >= len(lines):
            return
        
        line = lines[row]
        
        if col > 0:
            # Find word boundary
            import re
            text_before = line[:col]
            match = re.search(r'(\S+)$', text_before)
            
            if match:
                word_start = col - len(match.group(1))
                new_line = line[:word_start] + line[col:]
                lines[row] = new_line
                self.text = '\n'.join(lines)
                self.cursor_location = (row, word_start)
            else:
                # Delete single char/whitespace
                new_line = line[:col-1] + line[col:]
                lines[row] = new_line
                self.text = '\n'.join(lines)
                self.cursor_location = (row, col - 1)
        elif row > 0:
            # Join with previous line
            prev_line_len = len(lines[row - 1])
            lines[row - 1] = lines[row - 1] + lines[row]
            lines.pop(row)
            self.text = '\n'.join(lines)
            self.cursor_location = (row - 1, prev_line_len)
    
    def on_key(self, event: Key) -> None:
        """Handle key events with proper Unicode support."""
        key = event.key
        
        # Handle backspace - delete single Unicode character
        if key == "backspace":
            event.stop()
            self._delete_character_left()
            return
        
        # Handle Ctrl+Backspace - delete word
        if key == "ctrl+backspace" or key == "ctrl+h":
            event.stop()
            self._delete_word_left()
            return
        
        # Handle Ctrl+W
        if key == "ctrl+w":
            event.stop()
            self._delete_word_left()
            return
        
        # Let other keys pass through to parent class
        super().on_key(event)
