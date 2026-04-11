"""Search bar component for message search (less-style)."""

import re
from typing import Optional, Callable, List, Tuple
from textual.widgets import Static, Input
from textual.reactive import reactive
from textual.message import Message


class SearchMode(Message):
    """Message sent when search mode is toggled."""

    def __init__(self, active: bool):
        self.active = active
        super().__init__()


class SearchNavigate(Message):
    """Message sent to navigate to next/previous match."""

    def __init__(self, direction: int):  # 1 for next, -1 for previous
        self.direction = direction
        super().__init__()


class SearchBar(Static):
    """Search bar for searching through messages (less-style).

    Features:
    - Incremental search (search as you type)
    - Case-insensitive search
    - Regex support
    - Match counter (e.g., "3/12")
    - Navigation with n/N keys
    """

    DEFAULT_CSS = """
    SearchBar {
        height: 1;
        dock: bottom;
        background: $surface;
        color: $text;
        border-top: solid $border;
        padding: 0 1;
    }
    
    SearchBar Static.search-label {
        width: auto;
        color: $primary;
        text-style: bold;
    }
    
    SearchBar Input {
        width: 1fr;
        height: 1;
        border: none;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    
    SearchBar Input:focus {
        border: none;
    }
    
    SearchBar Static.match-count {
        width: auto;
        color: $text-muted;
        text-style: dim;
    }
    
    SearchBar Static.match-count.has-matches {
        color: $success;
        text-style: bold;
    }
    
    SearchBar Static.match-count.no-matches {
        color: $error;
    }
    
    SearchBar Static.help-text {
        width: auto;
        color: $text-muted;
        text-style: dim;
    }
    
    SearchBar.hidden {
        display: none;
    }
    """

    query: reactive[str] = reactive("")
    current_match: reactive[int] = reactive(0)
    total_matches: reactive[int] = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._input: Optional[Input] = None
        self._match_count: Optional[Static] = None
        self._search_results: List[Tuple[int, int, int]] = []  # (msg_idx, start, end)
        self._case_sensitive = False
        self._use_regex = False
        self._on_search: Optional[Callable[[str], List[Tuple[int, int, int]]]] = None
        self._on_navigate: Optional[Callable[[int], None]] = None

    def compose(self):
        """Compose the search bar."""
        yield Static("/", classes="search-label")
        self._input = Input(placeholder="search...")
        yield self._input
        self._match_count = Static("0/0", classes="match-count")
        yield self._match_count
        yield Static("(n/N to navigate, Esc to close)", classes="help-text")

    def on_mount(self):
        """Called when widget is mounted."""
        self.add_class("hidden")

    def show(self):
        """Show the search bar."""
        self.remove_class("hidden")
        if self._input:
            self._input.focus()
        self.post_message(SearchMode(True))

    def hide(self):
        """Hide the search bar."""
        self.add_class("hidden")
        self.post_message(SearchMode(False))

    def toggle(self):
        """Toggle search bar visibility."""
        if self.has_class("hidden"):
            self.show()
        else:
            self.hide()

    def on_input_changed(self, event: Input.Changed):
        """Handle input changes for incremental search."""
        self.query = event.value
        self._perform_search()

    def on_input_submitted(self, event: Input.Submitted):
        """Handle input submission (Enter key)."""
        self._navigate(1)  # Go to next match

    def _perform_search(self):
        """Perform the search."""
        if not self.query:
            self._search_results = []
            self.total_matches = 0
            self.current_match = 0
            self._update_match_count()
            return

        if self._on_search:
            self._search_results = self._on_search(self.query)
            self.total_matches = len(self._search_results)
            self.current_match = 1 if self.total_matches > 0 else 0
            self._update_match_count()

            # Navigate to first match
            if self.total_matches > 0 and self._on_navigate:
                self._on_navigate(0)

    def _update_match_count(self):
        """Update the match count display."""
        if not self._match_count:
            return

        if self.total_matches == 0:
            if self.query:
                self._match_count.update("no matches")
                self._match_count.add_class("no-matches")
                self._match_count.remove_class("has-matches")
            else:
                self._match_count.update("0/0")
                self._match_count.remove_class("has-matches", "no-matches")
        else:
            self._match_count.update(f"{self.current_match}/{self.total_matches}")
            self._match_count.add_class("has-matches")
            self._match_count.remove_class("no-matches")

    def _navigate(self, direction: int):
        """Navigate to next/previous match."""
        if self.total_matches == 0:
            return

        if direction == 1:  # Next
            self.current_match = self.current_match % self.total_matches + 1
        else:  # Previous
            self.current_match = (
                (self.current_match - 2 + self.total_matches) % self.total_matches
            ) + 1

        self._update_match_count()

        # Navigate to match
        if self._on_navigate and self._search_results:
            match_idx = self.current_match - 1
            self._on_navigate(match_idx)

    def action_next(self):
        """Go to next match (n key)."""
        self._navigate(1)
        self.post_message(SearchNavigate(1))

    def action_previous(self):
        """Go to previous match (N key)."""
        self._navigate(-1)
        self.post_message(SearchNavigate(-1))

    def action_close(self):
        """Close search bar (Esc key)."""
        self.hide()

    def set_search_callback(self, callback: Callable[[str], List[Tuple[int, int, int]]]):
        """Set the search callback function.

        The callback should accept a search query and return a list of
        (message_index, start_offset, end_offset) tuples.
        """
        self._on_search = callback

    def set_navigate_callback(self, callback: Callable[[int], None]):
        """Set the navigation callback function.

        The callback receives the index of the match to navigate to.
        """
        self._on_navigate = callback

    def search_in_text(self, text: str, query: str) -> List[Tuple[int, int]]:
        """Search for query in text, returning (start, end) positions.

        This is a helper method for performing searches.
        """
        if not query or not text:
            return []

        results = []
        flags = 0 if self._case_sensitive else re.IGNORECASE

        try:
            if self._use_regex:
                pattern = re.compile(query, flags)
                for match in pattern.finditer(text):
                    results.append((match.start(), match.end()))
            else:
                # Escape special regex characters for literal search
                escaped_query = re.escape(query)
                pattern = re.compile(escaped_query, flags)
                for match in pattern.finditer(text):
                    results.append((match.start(), match.end()))
        except re.error:
            # Invalid regex, fall back to literal search
            pattern = re.compile(re.escape(query), flags)
            for match in pattern.finditer(text):
                results.append((match.start(), match.end()))

        return results

    def focus_input(self):
        """Focus the search input."""
        if self._input:
            self._input.focus()

    def clear(self):
        """Clear the search query."""
        self.query = ""
        if self._input:
            self._input.value = ""
        self._search_results = []
        self.total_matches = 0
        self.current_match = 0
        self._update_match_count()
