"""TUI Components."""

from .prompt.input import PromptInput, PromptWithMode
from .message.display import MessageDisplay, MessageList
from .message.virtual_list import VirtualMessageList, HybridMessageList
from .status.bar import StatusBar
from .search_bar import SearchBar, SearchMode, SearchNavigate
from .diff_view import DiffView, DiffSummary, create_diff
from .session_fork import (
    SessionForkManager, 
    ForkDialog, 
    ForkNavigator, 
    SessionForked
)
from .frecency_history import (
    FrecencyHistory, 
    FrecencyInputHistory, 
    HistoryEntry
)

__all__ = [
    # Core components
    "PromptInput",
    "PromptWithMode",
    "MessageDisplay",
    "MessageList",
    "VirtualMessageList",
    "HybridMessageList",
    "StatusBar",
    # Search
    "SearchBar",
    "SearchMode",
    "SearchNavigate",
    # Diff
    "DiffView",
    "DiffSummary",
    "create_diff",
    # Session Fork
    "SessionForkManager",
    "ForkDialog",
    "ForkNavigator",
    "SessionForked",
    # History
    "FrecencyHistory",
    "FrecencyInputHistory",
    "HistoryEntry",
]
