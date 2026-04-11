"""Context Manager - Advanced context window management.

This module provides:
1. Context window size tracking
2. Token budget management
3. Auto-compact strategies
4. Smart truncation
5. Message prioritization
6. Context persistence

Features:
- Multiple compaction strategies (FIFO, LRU, Priority, Summarization)
- Token estimation per message
- Context window alerts
- Smart message selection for retention
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Any
from enum import Enum

from pydantic import BaseModel, Field


class CompactStrategy(str, Enum):
    """Strategy for compacting context."""

    FIFO = "fifo"  # First in, first out
    LRU = "lru"  # Least recently used
    PRIORITY = "priority"  # Keep high priority messages
    TOKEN_COUNT = "token_count"  # Remove largest messages first
    SUMMARIZATION = "summarization"  # Summarize old messages


class MessagePriority(int, Enum):
    """Message priority levels."""

    SYSTEM = 10  # System messages (always keep)
    USER_IMPORTANT = 8  # Important user messages
    ASSISTANT_IMPORTANT = 7  # Important assistant responses
    USER = 5  # Regular user messages
    ASSISTANT = 4  # Regular assistant responses
    TOOL = 3  # Tool results
    LOG = 1  # Log/debug messages (first to remove)


@dataclass
class ContextMessage:
    """A message in the context with metadata."""

    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    priority: MessagePriority = MessagePriority.USER
    tokens: int = 0
    id: str = field(default_factory=lambda: str(int(time.time() * 1000000)))
    metadata: dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    summarized: bool = False
    original_content: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "tokens": self.tokens,
            "id": self.id,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_access": self.last_access,
            "summarized": self.summarized,
            "original_content": self.original_content,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextMessage:
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            priority=MessagePriority(data.get("priority", 5)),
            tokens=data.get("tokens", 0),
            id=data.get("id", str(int(time.time() * 1000000))),
            metadata=data.get("metadata", {}),
            access_count=data.get("access_count", 0),
            last_access=data.get("last_access", time.time()),
            summarized=data.get("summarized", False),
            original_content=data.get("original_content"),
        )

    def touch(self) -> None:
        """Update access time and count."""
        self.access_count += 1
        self.last_access = time.time()


@dataclass
class ContextBudget:
    """Token budget configuration."""

    max_tokens: int = 8000
    warning_threshold: float = 0.8  # Warn at 80% capacity
    critical_threshold: float = 0.95  # Force compact at 95% capacity
    reserved_tokens: int = 500  # Reserve for system messages

    @property
    def warning_limit(self) -> int:
        return int(self.max_tokens * self.warning_threshold)

    @property
    def critical_limit(self) -> int:
        return int(self.max_tokens * self.critical_threshold)

    @property
    def available_tokens(self) -> int:
        return self.max_tokens - self.reserved_tokens


@dataclass
class ContextStats:
    """Context statistics."""

    total_messages: int = 0
    total_tokens: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    system_messages: int = 0
    tool_messages: int = 0
    compact_count: int = 0
    last_compact_time: Optional[float] = None
    average_message_size: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextConfig(BaseModel):
    """Configuration for ContextManager."""

    max_tokens: int = Field(default=8000, description="Maximum tokens in context")
    warning_threshold: float = Field(default=0.8, description="Warning threshold (0-1)")
    critical_threshold: float = Field(default=0.95, description="Critical threshold (0-1)")
    reserved_tokens: int = Field(default=500, description="Reserved tokens for system")
    compact_strategy: CompactStrategy = Field(
        default=CompactStrategy.PRIORITY, description="Default compaction strategy"
    )
    auto_compact: bool = Field(default=True, description="Auto-compact when critical")
    preserve_recent: int = Field(default=2, description="Number of recent exchanges to preserve")
    enable_summarization: bool = Field(default=True, description="Enable message summarization")


class ContextManager:
    """Manages conversation context with advanced features.

    Features:
    - Token budget management
    - Multiple compaction strategies
    - Message prioritization
    - Access tracking
    - Statistics

    Usage:
        manager = ContextManager(config)

        # Add messages
        manager.add_message("user", "Hello", priority=MessagePriority.USER)
        manager.add_message("assistant", "Hi there!")

        # Check status
        if manager.is_critical:
            manager.compact()

        # Get messages for model
        messages = manager.get_messages()
    """

    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.messages: list[ContextMessage] = []
        self.budget = ContextBudget(
            max_tokens=self.config.max_tokens,
            warning_threshold=self.config.warning_threshold,
            critical_threshold=self.config.critical_threshold,
            reserved_tokens=self.config.reserved_tokens,
        )
        self.stats = ContextStats()
        self._token_estimator: Optional[Callable[[str], int]] = None
        self._on_compact: Optional[Callable[[list[ContextMessage]], None]] = None
        self._on_warning: Optional[Callable[[int, int], None]] = None

    def set_token_estimator(self, estimator: Callable[[str], int]) -> None:
        """Set token estimation function."""
        self._token_estimator = estimator

    def set_compact_callback(self, callback: Callable[[list[ContextMessage]], None]) -> None:
        """Set callback for when messages are compacted."""
        self._on_compact = callback

    def set_warning_callback(self, callback: Callable[[int, int], None]) -> None:
        """Set callback for when approaching limit."""
        self._on_warning = callback

    def estimate_tokens(self, content: str) -> int:
        """Estimate tokens for content."""
        if self._token_estimator:
            return self._token_estimator(content)
        # Simple fallback: ~4 characters per token
        return len(content) // 4 + 1

    def add_message(
        self,
        role: str,
        content: str,
        priority: Optional[MessagePriority] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ContextMessage:
        """Add a message to context."""
        # Determine priority based on role if not specified
        if priority is None:
            priority = self._default_priority(role)

        # Create message
        message = ContextMessage(
            role=role,
            content=content,
            priority=priority,
            tokens=self.estimate_tokens(content),
            metadata=metadata or {},
        )

        # Add to context
        self.messages.append(message)
        self._update_stats()

        # Check thresholds
        if self.is_critical and self.config.auto_compact:
            self.compact()
        elif self.is_warning and self._on_warning:
            self._on_warning(self.stats.total_tokens, self.budget.warning_limit)

        return message

    def _default_priority(self, role: str) -> MessagePriority:
        """Get default priority for role."""
        priorities = {
            "system": MessagePriority.SYSTEM,
            "user": MessagePriority.USER,
            "assistant": MessagePriority.ASSISTANT,
            "tool": MessagePriority.TOOL,
        }
        return priorities.get(role, MessagePriority.LOG)

    def get_messages(
        self,
        include_summarized: bool = True,
        limit: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """Get messages in format for model API."""
        result = []

        for msg in self.messages:
            if not include_summarized and msg.summarized:
                continue

            result.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )
            msg.touch()

        if limit and len(result) > limit:
            result = result[-limit:]

        return result

    def get_context_messages(self) -> list[ContextMessage]:
        """Get raw context messages."""
        return self.messages.copy()

    @property
    def is_warning(self) -> bool:
        """Check if approaching token limit."""
        return self.stats.total_tokens >= self.budget.warning_limit

    @property
    def is_critical(self) -> bool:
        """Check if at critical token limit."""
        return self.stats.total_tokens >= self.budget.critical_limit

    @property
    def usage_ratio(self) -> float:
        """Get current usage ratio (0-1)."""
        return self.stats.total_tokens / self.budget.max_tokens

    def compact(
        self,
        strategy: Optional[CompactStrategy] = None,
        target_ratio: float = 0.7,
    ) -> list[ContextMessage]:
        """Compact context to reduce token usage.

        Args:
            strategy: Compaction strategy (default from config)
            target_ratio: Target usage ratio after compaction

        Returns:
            List of removed messages
        """
        strategy = strategy or self.config.compact_strategy
        target_tokens = int(self.budget.max_tokens * target_ratio)

        removed = []

        if strategy == CompactStrategy.FIFO:
            removed = self._compact_fifo(target_tokens)
        elif strategy == CompactStrategy.LRU:
            removed = self._compact_lru(target_tokens)
        elif strategy == CompactStrategy.PRIORITY:
            removed = self._compact_priority(target_tokens)
        elif strategy == CompactStrategy.TOKEN_COUNT:
            removed = self._compact_token_count(target_tokens)
        elif strategy == CompactStrategy.SUMMARIZATION:
            removed = self._compact_summarization(target_tokens)

        # Update stats
        self.stats.compact_count += 1
        self.stats.last_compact_time = time.time()
        self._update_stats()

        # Notify
        if removed and self._on_compact:
            self._on_compact(removed)

        return removed

    def _compact_fifo(self, target_tokens: int) -> list[ContextMessage]:
        """Remove oldest messages first."""
        removed = []

        # Preserve recent messages
        preserve_count = self.config.preserve_recent * 2  # User + assistant pairs
        removable = self.messages[:-preserve_count] if len(self.messages) > preserve_count else []

        for msg in list(removable):  # Use list() to avoid modifying during iteration
            if msg.priority == MessagePriority.SYSTEM:
                continue

            # Check current tokens
            current_tokens = sum(m.tokens for m in self.messages)
            if current_tokens <= target_tokens:
                break

            if msg in self.messages:
                self.messages.remove(msg)
                removed.append(msg)

        return removed

    def _compact_lru(self, target_tokens: int) -> list[ContextMessage]:
        """Remove least recently used messages."""
        removed = []

        # Sort by last access time
        removable = sorted(
            [m for m in self.messages if m.priority != MessagePriority.SYSTEM],
            key=lambda m: m.last_access,
        )

        # Preserve recent messages
        preserve_count = self.config.preserve_recent * 2
        removable = removable[:-preserve_count] if len(removable) > preserve_count else []

        for msg in list(removable):
            # Check current tokens
            current_tokens = sum(m.tokens for m in self.messages)
            if current_tokens <= target_tokens:
                break

            if msg in self.messages:
                self.messages.remove(msg)
                removed.append(msg)

        return removed

    def _compact_priority(self, target_tokens: int) -> list[ContextMessage]:
        """Remove lowest priority messages first."""
        removed = []

        # Sort by priority (ascending)
        removable = sorted(
            [m for m in self.messages if m.priority != MessagePriority.SYSTEM],
            key=lambda m: (m.priority.value, m.timestamp),
        )

        # Preserve recent messages
        preserve_count = self.config.preserve_recent * 2
        removable = removable[:-preserve_count] if len(removable) > preserve_count else []

        for msg in list(removable):
            # Check current tokens
            current_tokens = sum(m.tokens for m in self.messages)
            if current_tokens <= target_tokens:
                break

            if msg in self.messages:
                self.messages.remove(msg)
                removed.append(msg)

        return removed

    def _compact_token_count(self, target_tokens: int) -> list[ContextMessage]:
        """Remove largest messages first."""
        removed = []

        # Sort by token count (descending)
        removable = sorted(
            [m for m in self.messages if m.priority != MessagePriority.SYSTEM],
            key=lambda m: -m.tokens,
        )

        # Preserve recent messages
        preserve_count = self.config.preserve_recent * 2
        preserved_ids = (
            {m.id for m in self.messages[-preserve_count:]}
            if len(self.messages) > preserve_count
            else set()
        )

        for msg in list(removable):
            # Check current tokens
            current_tokens = sum(m.tokens for m in self.messages)
            if current_tokens <= target_tokens:
                break

            if msg.id in preserved_ids:
                continue

            if msg in self.messages:
                self.messages.remove(msg)
                removed.append(msg)

        return removed

    def _compact_summarization(self, target_tokens: int) -> list[ContextMessage]:
        """Summarize old messages instead of removing."""
        removed = []
        summarized = []

        # Find old messages to summarize
        now = time.time()
        old_threshold = 300  # 5 minutes

        for msg in self.messages:
            if msg.priority == MessagePriority.SYSTEM:
                continue

            if self.stats.total_tokens <= target_tokens:
                break

            # Only summarize non-summarized messages that are old
            if not msg.summarized and (now - msg.timestamp) > old_threshold:
                # Store original
                msg.original_content = msg.content
                msg.summarized = True

                # Create summary (in real implementation, this would use LLM)
                summary = f"[{msg.role}: {msg.content[:100]}...]"
                old_tokens = msg.tokens
                msg.content = summary
                msg.tokens = self.estimate_tokens(summary)

                saved_tokens = old_tokens - msg.tokens
                self.stats.total_tokens -= saved_tokens
                summarized.append(msg)

        # If still over limit, remove some
        if self.stats.total_tokens > target_tokens:
            removed = self._compact_priority(target_tokens)

        return removed + summarized

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._update_stats()

    def remove_message(self, message_id: str) -> bool:
        """Remove a specific message by ID."""
        for msg in self.messages:
            if msg.id == message_id:
                self.messages.remove(msg)
                self._update_stats()
                return True
        return False

    def get_message(self, message_id: str) -> Optional[ContextMessage]:
        """Get a specific message by ID."""
        for msg in self.messages:
            if msg.id == message_id:
                msg.touch()
                return msg
        return None

    def _update_stats(self) -> None:
        """Update context statistics."""
        self.stats.total_messages = len(self.messages)
        self.stats.total_tokens = sum(m.tokens for m in self.messages)
        self.stats.user_messages = sum(1 for m in self.messages if m.role == "user")
        self.stats.assistant_messages = sum(1 for m in self.messages if m.role == "assistant")
        self.stats.system_messages = sum(1 for m in self.messages if m.role == "system")
        self.stats.tool_messages = sum(1 for m in self.messages if m.role == "tool")

        if self.stats.total_messages > 0:
            self.stats.average_message_size = self.stats.total_tokens / self.stats.total_messages

    def get_stats(self) -> ContextStats:
        """Get current statistics."""
        self._update_stats()
        return self.stats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "config": self.config.model_dump(),
            "messages": [m.to_dict() for m in self.messages],
            "stats": self.stats.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextManager:
        """Deserialize from dictionary."""
        config = ContextConfig(**data.get("config", {}))
        manager = cls(config)

        for msg_data in data.get("messages", []):
            manager.messages.append(ContextMessage.from_dict(msg_data))

        manager._update_stats()
        return manager

    def save(self, filepath: str) -> None:
        """Save context to file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> ContextManager:
        """Load context from file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def __len__(self) -> int:
        """Return number of messages."""
        return len(self.messages)

    def __repr__(self) -> str:
        return f"ContextManager(messages={len(self.messages)}, tokens={self.stats.total_tokens})"


# Global instance management
_default_manager: Optional[ContextManager] = None


def get_context_manager(config: Optional[ContextConfig] = None) -> ContextManager:
    """Get or create global context manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ContextManager(config)
    return _default_manager


def clear_context_manager() -> None:
    """Clear the global context manager instance."""
    global _default_manager
    _default_manager = None


def create_context_manager(config: Optional[ContextConfig] = None) -> ContextManager:
    """Create a new context manager (not global)."""
    return ContextManager(config)
