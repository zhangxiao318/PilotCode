"""Query engine sub-managers.

This package contains extracted managers from QueryEngine:
- TokenManager: token counting, estimation, and budget tracking
- CompactionManager: context compaction pipeline
- PromptBuilder: system prompt construction
- MessageParser: XML tool-call fallback parsing
- SessionManager: save/load persistence
"""

from .token_manager import TokenManager
from .compaction_manager import CompactionManager
from .prompt_builder import PromptBuilder
from .message_parser import MessageParser
from .session_manager import SessionManager

__all__ = [
    "TokenManager",
    "CompactionManager",
    "PromptBuilder",
    "MessageParser",
    "SessionManager",
]
